import os
import time
import gtk
import glob
import string
import tempfile

import datetime
import pexpect

from imagefile import ImageFile
from cache import Cache, cached
from system import execute
from utils import locked

from threading import Lock

class VideoFile(ImageFile):
    description = "video"
    valid_extensions = ["avi","mp4","flv","wmv","mpg","mov","m4v","webm", "3gp"]
    video_cache = Cache(10)

    def __init__(self, filename):
        ImageFile.__init__(self, filename)
        self.lock = Lock()

    @cached()
    def get_metadata(self):
        info = [("Property", "Value")]
        output = execute(["avconv", "-i", self.get_filename()], check_retcode=False)
        for line in filter(lambda x: x, output.split("\n"))[4:]:
            tokens = list(map(string.strip, line.split(":")))
            if tokens[0].startswith("Stream"):
                break # Stop when avconv starts to dump streams metadata
            info.append((tokens[0], string.join(tokens[1:], ":")))
        return info

    @staticmethod
    def parse_duration(duration):
        try:
            st_time = time.strptime(duration.split(".")[0], "%H:%M:%S")
            delta = datetime.timedelta(hours=st_time.tm_hour,
                                       minutes=st_time.tm_min,
                                       seconds=st_time.tm_sec)
            return delta.seconds
        except:
            return int(duration)

    @cached()
    def get_duration(self):
        metadata = dict(self.get_metadata())
        if "Duration" in metadata:
            return self.parse_duration(metadata["Duration"])

        return 0

    @locked(lambda self: self.lock)
    @cached(video_cache)
    def get_pixbuf(self):
        second_cap = int(round(self.get_duration() * 0.2))
        tmp_root = os.path.join(tempfile.gettempdir(), "%s" % self.get_basename())
        tmp_img = "%s-000.jpg" % tmp_root

        try:
            self.extract_frame_at(second_cap, tmp_img)
        except:
            print("Warning: unable to extract thumbnail from '%s'" % self.get_basename())
            return self.get_empty_pixbuf()

        try:
            pixbuf = gtk.gdk.pixbuf_new_from_file(tmp_img)
            os.unlink(tmp_img)
            return pixbuf
        except:
            print("Warning: unable to open", tmp_img)
            return self.get_empty_pixbuf()

    def extract_frame_at(self, second, output):
        execute(["avconv", "-ss", str(second),
                 "-i", self.get_filename(),
                 "-vframes", "1",
                 "-an",
                 output])

    def get_sha1(self):
        # avoiding this for video files
        return "Duration: %s (%d seconds)" % (datetime.timedelta(seconds=self.get_duration()),
                                              self.get_duration())

    def extract_frames(self, offset, rate, count, tmp_dir):
        time_placeholder = "__TIME__"
        pattern = os.path.join(tmp_dir, "%s-%%06d%s.jpg" % (self.get_basename(),
                                                            time_placeholder))

        # Extract the frames:
        try:
            if not count:
                count = (self.get_duration()-offset) * rate
            child = pexpect.spawn("avconv", ["-ss", str(offset),
                                             "-i", self.get_filename(),
                                             "-r", str(rate),
                                             "-qscale", "1",
                                             "-vframes", str(count),
                                             pattern])
            first = True
            while True:
                child.expect("frame=")
                if not first:
                    tokens = [x for x in child.before.split(" ") if x]
                    frame = str(tokens[0])
                    yield float(frame) / count
                else:
                    first = False
        except pexpect.EOF:
            pass
        except Exception as e:
            print("Warning:", e)

        # Fill the placeholder in each file with the frame time:
        try:
            for filename in glob.glob(os.path.join(tmp_dir, "*")):
                index = filename.rindex(time_placeholder)
                frame = float(filename[index-6:index])-1

                time_ = (frame / rate) + offset
                hours, remainder = divmod(time_, 3600)
                minutes, seconds = divmod(remainder, 60)
                microseconds = (frame % rate) * ((10**6) * round(1.0/rate, 2))
                position = "%02d:%02d:%02d.%06d" % (hours, minutes, seconds, microseconds)

                os.rename(filename, filename.replace(time_placeholder, "-%s" % position))
                yield None
        except Exception as e:
            print("Warning:", e)

    def extract_contents(self, tmp_dir, offset, rate, count):
        return self.extract_frames(offset=offset,
                                   rate=rate,
                                   count=count,
                                   tmp_dir=tmp_dir)

    def can_be_extracted(self):
        return True

    def get_extract_args(self):
        return [("Offset", self.parse_duration, "offset", 0),
                ("Frame rate", float, "rate", 1.0),
                ("Frame count", int, "count", 0)]

