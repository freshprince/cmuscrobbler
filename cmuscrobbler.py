#!/usr/bin/env python

import sys
import time
import os
from datetime import datetime
import scrobbler

username = 'your last.fm username'
password = '5f4dcc3b5aa765d61d8327deb882cf99'
# to get yout passwort start python and enter:
# >>> from hashlib import md5
# >>> md5('password').hexdigest()
# '5f4dcc3b5aa765d61d8327deb882cf99'

class CmuScrobbler(object):
    def __init__(self):
        self.data = {}
        self.status = None
        self.status_content = None

        if self.status is None:
            self.status = "/tmp/cmuscrobbler-%s" % os.environ["USER"]

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

        if self.data['status'] == u'playing':
            self.submit_now_playing()
            self.write_file(now)
        else:
            if os.path.exists(self.status):
                os.remove(self.status)


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
        (file, artist, title, album, trackno, start, duration) = content.decode('utf-8').split("\t")
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

        # TODO: read mbid (MusicBrainz Track ID) from file
        # TODO: CACHEING

        scrobbler.login(username, password)
        scrobbler.submit(
            self.status_content['artist'],
            self.status_content['title'],
            now,
            source="P",
            length=int(self.status_content['duration']),
            album=self.status_content['album'],
            trackno=self.status_content['trackno'],
        )
        print scrobbler.flush()

    def submit_now_playing(self):
        if self.data['artist'] == u'' or self.data['title'] == u'':
            return
        scrobbler.login(username, password)
        scrobbler.now_playing(
            self.data['artist'],
            self.data['title'],
            album=self.data['album'],
            length=int(self.data['duration']),
            trackno=int(self.data['tracknumber']),
        )

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

