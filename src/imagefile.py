import os
import time
import shutil
import hashlib
import string

import gtk

from PIL import Image as PILImage
from PIL.ExifTags import TAGS as PILExifTags

from cache import Cache, cached
from system import trash, untrash, external_open

class ImageDimensions:
    def __init__(self, width, height):
        self.width = width
        self.height = height

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height

    def __str__(self):
        return "%dx%d" % (self.width, self.height)

    def __lt__(self, other):
        return (self.width * self.height) < (other.width * other.height)

class Size:
    def __init__(self, size):
        self.size = size

    def __str__(self):
        if self.size < 1024:
            return "%d bytes" % self.size
        elif self.size < (1024*1024):
            return "%.2f Kb" % (self.size/1024)
        else:
            return "%.2f Mb" % (self.size/(1024*1024))

    def __lt__(self, other):
        return self.size < other.size

class Datetime:
    def __init__(self, datetime):
        self.datetime = datetime

    def __lt__(self, other):
        return self.datetime < other.datetime

    def __str__(self):
        return time.strftime("%a %b %d %Y %X", time.localtime(self.datetime))

class File:
    star_marker = " (S)"

    def __init__(self, filename):
        self.filename = filename

    def get_filename(self):
        return self.filename

    def get_dirname(self):
        return os.path.dirname(self.filename)

    def get_basename(self):
        return os.path.basename(self.filename)

    def get_filesize(self):
        stat = os.stat(self.filename)
        size = stat.st_size
        return Size(size)

    @cached()
    def get_sha1(self):
        with open(self.filename, "r") as input_:
            return hashlib.sha1(input_.read()).hexdigest()

    def get_atime(self):
        return Datetime(os.stat(self.filename).st_atime)

    def get_mtime(self):
        return Datetime(os.stat(self.filename).st_mtime)

    def get_ctime(self):
        return Datetime(os.stat(self.filename).st_ctime)

    def __hash__(self):
        return hash(self.filename)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.filename == other
        elif isinstance(other, File):
            return self.filename == other.filename
        else:
            raise Exception("Can't compare File to " + repr(other))

    def copy(self, new_name):
        shutil.copy(self.filename, new_name)

    def rename(self, new_name):
        shutil.move(self.filename, new_name)
        self.filename = new_name

    def trash(self):
        trash(self.filename)

    def untrash(self):
        untrash(self.filename)

    def external_open(self):
        external_open(self.filename)

    def is_starred(self):
        name, sep, ext = self.get_basename().rpartition(".")
        return name.endswith(self.star_marker)

    def set_starred(self, starred):
        assert(self.is_starred() != starred)
        name, sep, ext = self.get_basename().rpartition(".")
        if starred:
            new_name = name + self.star_marker
        else:
            new_name = name.replace(self.star_marker, "")
        self.rename(os.path.join(self.get_dirname(),
                                 string.join((new_name, ext), sep)))

    def extract_contents(self, tmp_dir, **kw_args):
        pass

    def set_anim_enabled(self, enable):
        pass

    def can_be_extracted(self):
        return False

    def get_extract_args(self):
        return []

    def get_metadata(self):
        return []

class ImageFile(File):
    description = "image"
    pixbuf_cache = Cache(10)

    def __init__(self, filename):
        File.__init__(self, filename)
        self.rotation = 0
        self.flip_h = False
        self.flip_v = False

    def draw(self, widget, width, height):
        widget.set_from_pixbuf(self.get_pixbuf_at_size(width, height))

    @cached(pixbuf_cache)
    def get_pixbuf(self):
        try:
            return gtk.gdk.pixbuf_new_from_file(self.get_filename())
        except Exception as e:
            print("Warning:", e)
            return self.get_empty_pixbuf()

    def toggle_flip(self, horizontal):
        if horizontal:
            self.flip_h = not self.flip_h
        else:
            self.flip_v = not self.flip_v

    def rotate(self, clockwise):
        angle = (+90 if clockwise else -90)
        self.rotation = (self.rotation + angle) % 360

    def get_rotation(self):
        return (self.get_orientation() + self.rotation) % 360

    def get_pixbuf_at_size(self, width, height):
        angle_constants = {0: gtk.gdk.PIXBUF_ROTATE_NONE,
                           90: gtk.gdk.PIXBUF_ROTATE_CLOCKWISE,
                           180: gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN,
                           270: gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE}

        pixbuf = self.get_pixbuf()
        rotated = pixbuf.rotate_simple(angle_constants[self.get_rotation()])
        scaled = rotated.scale_simple(width, height, gtk.gdk.INTERP_BILINEAR)
        flipped = scaled.flip(True) if self.flip_h else scaled
        flipped = flipped.flip(False) if self.flip_v else flipped

        return flipped

    def get_dimensions(self):
        width, height = (self.get_pixbuf().get_width(),
                         self.get_pixbuf().get_height())

        if self.get_rotation() in (90, 270):
            width, height = height, width

        return ImageDimensions(width, height)

    def get_dimensions_to_fit(self, width, height):
        dimensions = self.get_dimensions()

        factor_w = float(width) / dimensions.get_width()
        factor_h = float(height) / dimensions.get_height()

        factor = min(factor_w, factor_h)

        width = int(dimensions.get_width() * factor)
        height = int(dimensions.get_height() * factor)

        return width, height

    @cached()
    def get_tags(self):
        tags = {}
        try:
            image = PILImage.open(self.get_filename())
            for tag, value in image._getexif().items():
                decoded = PILExifTags.get(tag, tag)
                tags[decoded] = value
        except Exception as e:
            pass
        return tags

    def get_metadata(self):
        tags = self.get_tags()
        if not tags:
            return None
        return [("Tag", "Value")] + sorted(tags.items())

    def get_orientation(self):
        # Orientation constants taken from:
        # http://sylvana.net/jpegcrop/exif_orientation.html
        angle_constants = {3: 180, 6: 90, 8: 270}
        orientation = self.get_tags().get("Orientation", 0)
        return angle_constants.get(orientation, 0)

    def get_empty_pixbuf(self):
        pixbuf = gtk.gdk.Pixbuf(colorspace=gtk.gdk.COLORSPACE_RGB,
                                has_alpha=False,
                                bits_per_sample=8,
                                width=1,
                                height=1)
        pixbuf.fill(0)
        return pixbuf

class EmptyImage(ImageFile):
    def __init__(self):
        ImageFile.__init__(self, "")

    def get_pixbuf(self):
        return self.get_empty_pixbuf()

    def get_pixbuf_at_size(self, width, height):
        return self.get_empty_pixbuf()

    def get_mtime(self):
        return "None"

    def get_filesize(self):
        return Size(0)

    def get_sha1(self):
        return "None"

class GTKIconImage(ImageFile):
    def __init__(self, stock_id, size):
        ImageFile.__init__(self, "")
        self.stock_id = stock_id
        self.size = size

    def get_pixbuf(self):
        theme = gtk.icon_theme_get_default()
        return theme.load_icon(self.stock_id, self.size, 0)

    def __repr__(self):
        return "GTKIconImage(%s, %d)" % (self.stock_id, self.size)

    def get_pixbuf_at_size(self, width, height):
        theme = gtk.icon_theme_get_default()
        return theme.load_icon(self.stock_id, width, 0)

    def get_dimensions(self):
        return ImageDimensions(self.size, self.size)
