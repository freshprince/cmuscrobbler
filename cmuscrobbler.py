#!/usr/bin/env python
# cmuscrobbler.py - Scrobble your Songs that you listened to in Cmus
#    Copyright (C) 2008  David Flatz
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
from datetime import datetime
import scrobbler

username = 'your last.fm username'
password = '5f4dcc3b5aa765d61d8327deb882cf99'
cachefile = '/path/to/cachefile'

# to get yout passwort start python and enter:
# >>> from hashlib import md5
# >>> md5('password').hexdigest()
# '5f4dcc3b5aa765d61d8327deb882cf99'

class CmuScrobbler(object):
    def __init__(self):
        self.data = {}
        self.status = None
        self.status_content = None
        self.pidfile = None

        if self.status is None:
            self.status = '/tmp/cmuscrobbler-%s.status' % os.environ['USER']
        if self.pidfile is None:
            self.pidfile = '/tmp/cmuscrobbler-%s.pid' % os.environ['USER']

    def get_status(self):
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
                    os.remove(self.status)
                    self.submit()
                return

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
            }
        else:
            if os.path.exists(self.status):
                os.remove(self.status)

        self.commit(now_playing)


    def read_arguments(self):
        self.data = dict(zip(sys.argv[1::2], map(lambda x: x.decode('utf-8'), sys.argv[2::2])))
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


    def read_file(self):
        if not os.path.exists(self.status):
            return
        fo = open(self.status, "r")
        content = fo.read()
        fo.close()
        (file, artist, title, album, trackno, start, duration) = content.decode('utf-8').strip().split("\t")
        self.status_content = {'file': file,
                               'artist': artist,
                               'title': title,
                               'album': album,
                               'trackno': trackno,
                               'start': int(start),
                               'duration': int(duration)}


    def write_file(self, start):
        to_write = u'\t'.join((
            self.data['file'],
            self.data['artist'],
            self.data['title'],
            self.data['album'],
            self.data['tracknumber'],
            str(start),
            self.data['duration']))
        fo = open(self.status, "w")
        fo.write(to_write.encode('utf-8'))
        fo.write('\n')
        fo.close()


    def submit(self):
        #submits track if it got played long enough
        if self.status_content['artist'] == u'' or self.status_content['title'] == u'':
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
            return

        # TODO: read mbid (MusicBrainz Track ID) from file save filename and read it in the fork
        # also do this for now_playing
        to_write = u'\t'.join((
            self.status_content['artist'],
            self.status_content['title'],
            str(now),
            u'P',
            str(self.status_content['duration']),
            self.status_content['album'],
            self.status_content['trackno']))
        fp = file(cachefile,'a')
        fp.write(to_write.encode('utf-8'))
        fp.write('\n')
        fp.close()

    def commit(self, now_playing=None):
        if os.path.exists(self.pidfile):
            "commit already running maybe waiting for network timeout or something, doing nothing"
            return
        if not os.fork():
            os.setsid()
            pid = os.fork()
            if pid:
                fo = file(self.pidfile, 'w')
                fo.write(str(pid))
                fo.close()
                sys.exit(0)
            else:
                self._real_commit(now_playing)

    def _real_commit(self, now_playing):
        try:
            scrobbler.login(username, password)
            if os.path.exists(cachefile):
                # TODO: try several times (3?) with delay (exponentional?)
                fo = file(cachefile,'r')
                line = fo.readline()
                while len(line) > 0:
                    (artist, track, time, source, length, album, trackno) = line.decode('utf-8').strip().split('\t')
                    scrobbler.submit(artist, track, int(time),
                        source=source,
                        length=int(length),
                        album=album,
                        trackno=int(trackno),
                    )
                    line = fo.readline()
                fo.close()
                scrobbler.flush()
                os.remove(cachefile)
            if now_playing is not None and not now_playing['artist'] == u'' and not now_playing['title'] == u'':
                scrobbler.now_playing(
                    now_playing['artist'],
                    now_playing['title'],
                    album=now_playing['album'],
                    length=int(now_playing['length']),
                    trackno=int(now_playing['trackno']),
                )
        finally:
            if os.path.exists(self.pidfile):
                os.remove(self.pidfile)

def exception_hook(*exc_info):
    if exc_info == ():
        exc_info = sys.exc_info()
    fp = file('/tmp/cmuscrobbler-%s.error' % os.environ['USER'], 'a')
    fp.write(cgitb.text(exc_info))
    fp.close()

sys.excepthook = exception_hook

def usage():
    print "To use cmuscrobbler.py:"
    print "Use it as status_display_program in cmus"
    print "\n type :set status_display_program=/patch/to/cmuscrobbler.py\n"
    print "Don't forget to add your username and password in the script."

if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage()
        sys.exit()
    cs = CmuScrobbler()
    cs.get_status()

