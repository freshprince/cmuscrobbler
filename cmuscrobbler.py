#!/usr/bin/env python
# cmuscrobbler.py - Scrobble your Songs that you listened to in Cmus
#    Copyright (C) 2008-2010  David Flatz
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import time
import os
import cgitb
import traceback
import logging
from datetime import datetime
from urllib import quote, unquote
import scrobbler
import mutagen
from mutagen.id3 import ID3
import ConfigParser

# You can also configure the following variables using ~/.cmuscrobbler.conf,
# see INSTALL.

scrobbler_config = [
    { 'username':      'your last.fm username',
      'password':      '5f4dcc3b5aa765d61d8327deb882cf99',
      'cachefile':     '/path/to/last.fm/cachefile',
      'scrobbler_url': 'http://post.audioscrobbler.com/',
      'pidfile':       '/path/to/last.fm/pidfile',
    },
#    { 'username':      'your libre.fm username',
#      'password':      '5f4dcc3b5aa765d61d8327deb882cf99',
#      'cachefile':     '/path/to/libre.fm/cachefile',
#      'scrobbler_url': 'http://turtle.libre.fm/',
#      'pidfile':       '/path/to/libre.fm./pidfile',
#    },
]

# set this to False if you don't like to use the 'now playing' function
do_now_playing = True

# to get yout passwort start python and enter:
# >>> from hashlib import md5
# >>> md5('password').hexdigest()
# '5f4dcc3b5aa765d61d8327deb882cf99'

debug = False
debuglogfile = '/path/to/logfile'

# --- end of configuration variables ---
logger = logging.getLogger('cmuscrobbler')

def log_traceback(exception):
    if not debug:
        return
    for tbline in traceback.format_exc().splitlines():
        logger.debug('%s', tbline)

def get_mbid(file):
    try:
        if mutagen.version >= (1,17):
            f = mutagen.File(file, easy=True)
            mbid = f.get('musicbrainz_trackid', '')
            if not isinstance(mbid, basestring):
                mbid = mbid[0]
            return str(mbid)
        else:
            audio = ID3(file)
            ufid = audio.get(u'UFID:http://musicbrainz.org')
            return ufid.data if ufid else ''
    except Exception, e:
        logger.debug('get_mbid failed: %s', e)
        return ''

class CmuScrobbler(object):

    CLIENTID = ('cmu','1.0')

    def __init__(self):
        self.data = {}
        self.status = None
        self.status_content = None
        if self.status is None:
            self.status = '/tmp/cmuscrobbler-%s.status' % os.environ['USER']

    def get_status(self):
        logger.debug('Main Process initialiated')
        self.read_arguments()
        self.read_file()

        now = int(time.mktime(datetime.now().timetuple()))

        """
            The track must be submitted once it has finished playing. Whether
            it has finished playing naturally or has been manually stopped by
            the user is irrelevant.
        """
        if self.status_content is not None:
            if self.status_content['file'] == self.data['file']:
                if self.data['status'] != u'playing' and os.path.exists(self.status):
                    logger.info('Not playing. Removing statusfile')
                    os.remove(self.status)
            self.submit()

        now_playing = None
        if self.data['status'] == u'playing':
            self.write_file(now)
            now_playing = {
                'artist': self.data['artist'],
                'title': self.data['title'],
                'album': self.data['album'],
                'length': self.data['duration'],
                'trackno': self.data['tracknumber'],
                'file': self.data['file'],
            }
        else:
            if os.path.exists(self.status):
                os.remove(self.status)

        self.commit(now_playing)
        logger.debug('Main Process finished.')


    def read_arguments(self):
        for k, v in zip(sys.argv[1::2], sys.argv[2::2]):
            try:
                self.data[k] = v.decode('utf-8')
            except UnicodeDecodeError:
                # if utf-8 fails try with latin1.
                # FIXME: consider making this configurable
                self.data[k] = v.decode('latin1')
        # self.data will be a hash like this:
        """
        {'album': u'Basics',
         'artist': u'Funny van Dannen',
         'duration': u'147',
         'file': u'/home/david/m/m/+DB/Funny_van_Dannen/Basics/01-Guten_Abend.mp3',
         'status': u'stopped',
         'title': u'Guten Abend',
         'tracknumber': u'1'}
        """
        for field in ['artist', 'title', 'album', 'tracknumber', 'status', 'file']:
            if not self.data.has_key(field):
                self.data[field] = u''
        logger.debug('Got Arguments: %s', self.data)


    def read_file(self):
        if not os.path.exists(self.status):
            return
        fo = open(self.status, "r")
        content = fo.read()
        fo.close()
        (file, artist, title, album, trackno, start, duration) = content.split("\t")
        duration = duration.strip()
        self.status_content = {'file': unquote(file).decode('utf-8'),
                               'artist': unquote(artist).decode('utf-8'),
                               'title': unquote(title).decode('utf-8'),
                               'album': unquote(album).decode('utf-8'),
                               'trackno': trackno.decode('utf-8'),
                               'start': int(start),
                               'duration': int(duration)}
        logger.debug('Got statusinfo: %s', self.status_content)


    def write_file(self, start):
        to_write = '\t'.join((
            quote(self.data['file'].encode('utf-8')),
            quote(self.data['artist'].encode('utf-8')),
            quote(self.data['title'].encode('utf-8')),
            quote(self.data['album'].encode('utf-8')),
            self.data['tracknumber'].encode('utf-8'),
            str(start).encode('utf-8'),
            self.data['duration'].encode('utf-8')))
        fo = open(self.status, "w")
        fo.write(to_write)
        fo.write('\n')
        fo.close()
        logger.info('Wrote statusfile.')
        logger.debug('Content: %s', to_write)


    def submit(self):
        #submits track if it got played long enough
        if self.status_content['artist'] == u'' or self.status_content['title'] == u'':
            logger.info('Not submitting because artist or title is empty')
            return

        now = int(time.mktime(datetime.now().timetuple()))

        """ The track must have been played for a duration of at least 240
            seconds *or* half the track's total length, whichever comes first.
            Skipping or pausing the track is irrelevant as long as the
            appropriate amount has been played.

            The total playback time for the track must be more than 30 seconds.
            Do not submit tracks shorter than this.
        """
        if (self.status_content['duration'] <= 30 or
                now - self.status_content['start'] < min(int(round(self.status_content['duration']/2.0)), 240)):
            logger.info('Not submitting because didn\'t listen to long enough')
            return

        to_write = '\t'.join((
            quote(self.status_content['file'].encode('utf-8')),
            quote(self.status_content['artist'].encode('utf-8')),
            quote(self.status_content['title'].encode('utf-8')),
            str(now).encode('utf-8'),
            'P',
            str(self.status_content['duration']).encode('utf-8'),
            quote(self.status_content['album'].encode('utf-8')),
            self.status_content['trackno']))
        for config in scrobbler_config:
            cachefile = config.get('cachefile')
            if cachefile is None:
                raise Exception('Broken config! Cachefile missing.')
            fp = file(cachefile,'a')
            fp.write(to_write)
            fp.write('\n')
            fp.close()
            logger.info('Attached submit to cachefile %s' % cachefile)
        logger.debug('Content: %s', to_write)

    def commit(self, now_playing=None):
        for config in scrobbler_config:
            pidfile = config.get('pidfile')
            password = config.get('password')
            scrobbler_url = config.get('scrobbler_url')
            username = config.get('username')
            cachefile = config.get('cachefile')
            if ((pidfile is None) or (password is None) or (scrobbler_url is None) or (username is None) or (cachefile is None)):
                raise Exception('Broken config! Something is missing.')

            if os.path.exists(pidfile):
                "commit already running maybe waiting for network timeout or something, doing nothing"
                logger.info('Commit already running. Not commiting. (%s)' % pidfile)
                continue

            logger.debug('Forking')
            if not os.fork():
                os.setsid()
                pid = os.fork()
                if pid:
                    fo = file(pidfile, 'w')
                    fo.write(str(pid))
                    fo.close()
                    logger.debug('Wrote pidfile')
                    sys.exit(0)
                else:
                    try:
                        self._real_commit(now_playing, cachefile, username, password, scrobbler_url)
                    finally:
                        if os.path.exists(pidfile):
                            os.remove(pidfile)
                            logger.debug('Deleted pidfile')


    def _real_commit(self, now_playing, cachefile, username, password, scrobbler_url):
        """this is quite ugly spaghetti code. maybe we could make this a little bit more tidy?"""
        logger.info('Begin scrobbling to %s', scrobbler_url)
        if (not do_now_playing):
            logger.debug('Now playing disabled')
            now_playing = None
        success = False
        tosubmit = set()
        tosubmitted = set()
        cache_count = 0
        retry_sleep = None
        retry_count = 0
        while not success:
            if retry_sleep is None:
                retry_sleep = 60
            else:
                retry_count = retry_count + 1
                if retry_count > 7:
                    logger.info('Giving up scrobbling to %s', scrobbler_url)
                    break
                logger.info('Sleeping %d minute(s)', retry_sleep / 60)
                time.sleep(retry_sleep)
                retry_sleep = min(retry_sleep * 2, 120 * 60)
            #handshake phase
            logger.debug('Handshake')
            try:
                scrobbler.login(username, password, hashpw=False, client=CmuScrobbler.CLIENTID, url=scrobbler_url)
            except Exception, e:
                logger.error('Handshake with %s failed: %s', scrobbler_url, e)
                log_traceback(e)
                continue

            #submit phase
            if os.path.exists(cachefile):
                logger.info('Scrobbling songs to %s', scrobbler_url)
                (_, _, _, _, _, _, _, _, mtime, _) = os.stat(cachefile)
                fo = file(cachefile,'r')
                line = fo.readline()
                while len(line) > 0:
                    try:
                        (path, artist, track, playtime, source, length, album, trackno) = line.split('\t')
                        trackno = trackno.strip()
                        mbid = get_mbid(unquote(path).decode('utf-8'))
                        tosubmit.add((playtime, artist, track, source, length, album, trackno, mbid))
                    except Exception, e:
                        logger.debug('cache read error: %s', e)
                    line = fo.readline()
                fo.close()
                logger.info('Read %d songs from cachefile %s', len(tosubmit), cachefile)

                logger.debug('Sorting songlist')
                submitlist = list(tosubmit)
                submitlist.sort(key=lambda x: int(x[0]))
                retry = False
                for (playtime, artist, track, source, length, album, trackno, mbid) in submitlist:
                    if (playtime, artist, track, source, length, album, trackno, mbid) in tosubmitted:
                        logger.debug('Track already submitted or in cache: %s - %s', unquote(artist), unquote(track))
                        continue
                    if cache_count >= 3:
                        logger.info('Flushing. cache_count=%d', cache_count)
                        if self._flush():
                            logger.info('Flush successful.')
                            retry_sleep = None
                            cache_count = 0
                        else:
                            retry = True
                            break
                    sb_success = False
                    for tries in xrange(1, 4):
                        logger.debug('Try to submit: %s, %s, playtime=%d, source=%s, length=%s, album=%s, trackno=%s, mbid=%s',
                            unquote(artist), unquote(track), int(playtime), source, length, unquote(album), trackno, mbid)
                        try:
                            sb_success = scrobbler.submit(unquote(artist).decode('utf-8'), unquote(track).decode('utf-8'),
                                int(playtime),
                                source=source.decode('utf-8'),
                                length=length.decode('utf-8'),
                                album=unquote(album).decode('utf-8'),
                                trackno=trackno.decode('utf-8'),
                                mbid=mbid,
                            )
                        except Exception, e:
                            logger.error('Submit error: %s', e)
                            log_traceback(e)
                            sb_success = False
                        if sb_success:
                            tosubmitted.add((playtime, artist, track, source, length, album, trackno, mbid))
                            cache_count += 1
                            logger.info('Submitted. cache_count=%d: %s - %s', cache_count, unquote(artist), unquote(track))
                            break
                        logger.error('Submit failed. Try %d', tries)
                    if not sb_success:
                       retry = True
                       break
                    if cache_count >= 3:
                        logger.info('Flushing. cache_count=%d', cache_count)
                        if self._flush():
                            logger.info('Flush successful.')
                            retry_sleep = None
                            cache_count = 0
                        else:
                            retry = True
                            break
                if retry:
                    logger.error('Restaring')
                    continue

                if cache_count > 0:
                    logger.info('Cache not empty: flushing')
                    if self._flush():
                        logger.info('Flush successful.')
                        retry_sleep = None
                        cache_count = 0
                    else:
                        logger.error('Restarting')
                        continue

                (_, _, _, _, _, _, _, _, newmtime, _) = os.stat(cachefile)
                if newmtime != mtime:
                    logger.info('Cachefile changed since we started. Restarting')
                    continue
                logger.info('Scrobbled all Songs, removing cachefile')
                os.remove(cachefile)

            #now playing phase
            if now_playing is not None and not now_playing['artist'] == u'' and not now_playing['title'] == u'':
                logger.info('Sending \'Now playing\' to %s', scrobbler_url)
                mbid = get_mbid(now_playing['file'])
                np_success = False
                for tries in xrange(1, 4):
                    try:
                        if len(now_playing['trackno']) == 0:
                            now_playing['trackno'] = '0'
                        np_success = scrobbler.now_playing(
                            now_playing['artist'],
                            now_playing['title'],
                            album=now_playing['album'],
                            length=int(now_playing['length']),
                            trackno=int(now_playing['trackno']),
                            mbid=mbid,
                        )
                    except Exception, e:
                        logger.error('now_playing threw an exception: %s' % e)
                        log_traceback(e)
                        break
                    if np_success:
                        logger.info('\'Now playing\' submitted successfully')
                        retry_sleep = None
                        now_playing = None
                        break
                    logger.error('Sending \'Now playing\' failed. Try %d', tries)
                if not np_success:
                    logger.error('Submitting \'Now playing\' failed. Giving up.')

            success = True
        logger.info('Finished scrobbling to %s', scrobbler_url)

    def _flush(self):
        sb_success = False
        for tries in xrange(1, 4):
            try:
                sb_success = scrobbler.flush()
            except Exception, e:
                logger.error('Flush error: %s', e)
                log_traceback(e)
                sb_success = False
            if sb_success:
                break
            logger.error('Flush failed. try %d', tries)
        return sb_success

def exception_hook(*exc_info):
    if exc_info == ():
        exc_info = sys.exc_info()
    fp = file('%s-error' % debuglogfile, 'a')
    fp.write(cgitb.text(exc_info))
    fp.close()
    logger.critical('ERROR EXIT -- see %s-error for detailed traceback' % debuglogfile)
    for tbline in traceback.format_exc().splitlines():
        logger.debug('%s', tbline)

def read_config():
    global do_now_playing, debug, debuglogfile
    cp = ConfigParser.SafeConfigParser({'home': os.getenv('HOME')})
    cp.read(os.path.expanduser('~/.cmus/cmuscrobbler.conf'))
    cp.read(os.path.expanduser('~/.cmuscrobbler.conf'))
    if cp.sections():
        scrobbler_config[:] = [dict(cp.items(n)) for n in cp.sections()]
    if 'do_now_playing' in cp.defaults():
        do_now_playing = cp.getboolean('DEFAULT', 'do_now_playing')
    if 'debug' in cp.defaults():
        debug = cp.getboolean('DEFAULT', 'debug')
    if 'debuglogfile' in cp.defaults():
        debuglogfile = cp.get('DEFAULT', 'debuglogfile')

def usage():
    print "To use cmuscrobbler.py:"
    print "Use it as status_display_program in cmus"
    print "\n type :set status_display_program=/patch/to/cmuscrobbler.py\n"
    print "Don't forget to add your username and password in the script or in"
    print "~/.cmuscrobbler.conf or ~/.cmus/cmuscrobbler.conf."

if __name__ == "__main__":
    read_config()

    if debug:
        FORMAT = "%(asctime)-15s %(process)d %(levelname)-5s: %(message)s"
        logging.basicConfig(filename=debuglogfile, level=logging.DEBUG, format=FORMAT)
        sys.excepthook = exception_hook
    else:
        logging.basicConfig(filename='/dev/null')

    if len(sys.argv) < 2:
        usage()
        sys.exit()
    cs = CmuScrobbler()
    cs.get_status()

