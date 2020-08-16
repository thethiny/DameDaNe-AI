import argparse
import sys

CHANGELOG = {
    "1.0": ["Initial Release"],
    "1.1": [
        "Added support for AAC encoding so that it works on iphone.",
        "Encoding now is outputted in the output video name.",
        "Added \"--stacked\" argument",
        "Reformatted Output"
    ]
}

RELEASES = sorted(CHANGELOG.keys())

class ChangelogAction(argparse.Action):
    def __init__(self, *args, **kwargs):
        super(ChangelogAction, self).__init__(*args, **kwargs)
    def __call__(self, parser, namespace, values, option_string=None):
        if values == 'all':
            changelog_loop = RELEASES
        else:
            changelog_loop = [values]
        for release in changelog_loop:
            print("Changelog for version", release, end = ':\n')
            for line in CHANGELOG[release]:
                print('-',  line)
            print()
        sys.exit(0)


parser = argparse.ArgumentParser(description="Generate video from image with audio support")
input_group = parser.add_argument_group("Input", "Arguments for Video and Image Inputs")
input_group.add_argument("-s", "--source", type=str, help="The Image to generate a video from", required=True)
input_group.add_argument("-v", "--video", type=str, help="The driver to use to make the video", required=True)
input_group.add_argument("-m", "--mode", type=str.lower, help="The generation mode, defaults to face movement", default="vox",
    choices=["fashion", "vox", "vox-advanced", "gif"])

flags_group = parser.add_argument_group("Flags", "Flags that enable or disable specific modes")
flags_group.add_argument("--adaptive", "--adapt", action="store_true", help="Adaptive Movement Scale", default=False)
flags_group.add_argument("--stack", "--stacked", action="store_true", help="Create a video with input and output side by side", default=False)

resize_group = parser.add_argument_group("Resize", "Modes for resizing inputs")
resize_group.add_argument("-ir", "--image-resize", help="Resize mode for resizing source image", default="stretch",
    choices=["fill", "stretch", "crop"], type=str.lower)
resize_group.add_argument("-vr", "--video-resize", help="Resize mode for resizing source video", default="stretch",
    choices=["fill", "stretch", "crop"], type=str.lower)

time_group = parser.add_argument_group("Time Remap", "Arguments to select start, end, and video duration")
time_group.add_argument('--start', help="Set Video Start", default=0.00, type=float)
duration_group = time_group.add_mutually_exclusive_group()
duration_group.add_argument('--duration', help="Set Video Duration", default=0.00, type=float)
duration_group.add_argument('--end', help="Set Video End", default=0.00, type=float)

codecs_group = parser.add_argument_group("Codecs", "Arguments to choose codec groups.")
platform_release = codecs_group.add_mutually_exclusive_group()
platform_release.add_argument("-c", "--codec", type=str.lower, help="Choose Codec Mode. MPEG4 is the least compatible. H264 is compatible with most devices. MP4 is Python's default format, doesn't work on some devices.", default="h264", 
    choices=["h264", "mpeg4", "mp4"])

changelog_group = parser.add_argument_group("Version Info", "Version related information")
changelog_group.add_argument('--version', action='version', help="Prints current version", version='%(prog)s version ' + RELEASES[-1])
#changelog_group.add_argument('--changelog', type=str.lower, help="See the changelog for this version", choices = RELEASES + ['all'])
changelog_group.add_argument('--changelog', type=str.lower, help="See the changelog for this version", choices = RELEASES + ['all'], action=ChangelogAction)

args = parser.parse_args()


import warnings
from os import makedirs
from os.path import basename, join, splitext, isfile
from sys import argv

import imageio
import numpy as np
from skimage import img_as_ubyte
from skimage.transform import resize
from skimage.util import crop as image_crop
from skimage.util import pad as image_pad

import moviepy.config as mpy_conf
import webp
from demo import load_checkpoints, make_animation
from moviepy.editor import clips_array
from moviepy.video.fx.all import crop as movie_crop
from moviepy.video.fx.all import margin as movie_margin
from moviepy.video.fx.all import resize as movie_resize
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import VideoClip

output_folder = "output"
#FFMPEG_BINARY_AAC = "ffmpeg-hi10-heaac.exe"
FFMPEG_BINARY_AAC = "ffmpeg.exe"

warnings.filterwarnings("ignore")

options = {
    'relative': None,
    'adapt_movement_scale': None
}

modes = {
    "fashion": {
        "config_path": "config/fashion-256.yaml",
        "checkpoint_path": 'checkpoints/fashion.pth.tar'
    },
    "vox": {
        "config_path": "config/vox-256.yaml",
        "checkpoint_path": 'checkpoints/vox-cpk.pth.tar'
    },
    "vox-advanced": {
        "config_path": "config/vox-256.yaml",
        "checkpoint_path": 'checkpoints/vox-adv-cpk.pth.tar'
    },
    "gif": {
            "config_path": "config/mgif-256.yaml",
            "checkpoint_path": 'checkpoints/mgif-cpk.pth.tar'
    },
}

codecs = {
    'h264': {
        'codec': 'libx264',
        'audio_codec': 'libfdk_aac'
    },
    'mp4':
    {
        'codec': 'libx264',
        'audio_codec': 'libmp3lame'
    },
    'mpeg4':
    {
        'codec': 'mpeg4',
        'audio_codec': 'libfdk_aac'
    }
    
}

codec_names = {
    'h264': {
        'video': 'h.264',
        'audio': 'm4a'
    },
    'mp4':
    {
        'video': 'h.264',
        'audio': 'mp3'
    },
    'mpeg4':
    {
        'video': 'MPEG4',
        'audio': 'm4a'
    }
}

def get_codec_info(codec):
    if codec == 'libx264':
        return 'h.264'
    if codec == 'mpeg4':
        return 'MPEG4'
    if codec == 'libmp3lame':
        return 'MP3'
    if codec == 'libfdk_aac':
        return 'AAC'

if codecs[args.codec]['audio_codec'] == 'libfdk_aac':
    if not isfile(FFMPEG_BINARY_AAC):
        raise Exception("libfdk_aac is required, please download " + FFMPEG_BINARY_AAC + '.')
    mpy_conf.change_settings({'FFMPEG_BINARY': FFMPEG_BINARY_AAC})

print("Generation Mode:", args.mode.capitalize())
print("Generation Video Codec:", get_codec_info(codecs[args.codec]['codec']))
print("Generation Audio Codec:", get_codec_info(codecs[args.codec]['audio_codec']))

if args.adaptive:
    options['adapt_movement_scale'] = True
    options['relative'] = False
    print("Generation Scale: Adaptive")
else:
    options['adapt_movement_scale'] = False
    options['relative'] = True
    print("Generation Scale: Relative")
print()

source_image_path = args.source
driving_video_path = args.video
output_video_name, image_extension = basename(source_image_path).rsplit('.', 1)
output_video_name += '_' + args.image_resize + '_' + args.video_resize
if options['adapt_movement_scale']:
    output_video_name += '_adaptive_scaling'
output_video_name += "_" + args.codec
output_video_name += ".mp4"
driving_video_name = basename(driving_video_path).rsplit('.', 1)[0]
output_folder = join(output_folder, driving_video_name)
try:
    makedirs(output_folder)
except:
    pass
output_video_path = join(output_folder, output_video_name)

print("Loading Model")
generator, kp_detector = load_checkpoints(**modes[args.mode])
print("Loading User Input")
print()

# Read Video and Extract Audio
source_video = VideoFileClip(driving_video_path)
# Remap timings
if args.start:
    if args.end and args.end > args.start and args.end < source_video.duration:
            source_video = source_video.subclip(args.start, args.end)
    elif args.duration and args.duration < source_video.duration and args.duration + args.start < source_video.duration:
            source_video = source_video.subclip(args.start, args.start + args.duration)            
    else:
        if args.start < source_video.duration:
            source_video = source_video.subclip(args.start)
        else:
            args.start = 0.00
else:
    if args.end and args.end < source_video.duration:
        source_video = source_video.subclip(source_video.start, args.end)
    elif args.duration and args.duration < source_video.duration:
        source_video = source_video.subclip(source_video.start, source_video.start + args.duration)

source_audio = source_video.audio
source_fps = source_video.fps
source_duration = source_video.duration
print("Video Info:")
print("Name:", driving_video_path)
print("Dimensions:", 'x'.join([str(x) for x in source_video.size]))
print("Start:", args.start or source_video.start)
print("Duration:", source_duration)
print("End:", (args.start or source_video.start) + source_duration)
print("FPS:", source_fps)
print()
# Read Image
if image_extension.lower() == 'webp':
    source_image = np.array(webp.load_image(source_image_path, 'RGBA'))
else:
    source_image = imageio.imread(source_image_path)

print("Image Info:")
print("Name:", source_image_path)
print("Dimensions:", 'x'.join([str(x) for x in source_image.shape[:2]]))
print()

# Read and Resize image and video to 256x256
if source_image.shape[:2] != [256, 256]:
    print("Resizing image to 256x256 with ", end = '')
    if args.image_resize == 'fill':
        print("Mode: Fill")
        width, height = source_image.shape[:2]
        if width > height:
            height = int(256*height / width)
            width = 256
            source_image = resize(source_image, (width, height))[..., :3]
            remaining = 256-height
            side_1 = int(remaining/2)
            side_2 = int(remaining - side_1)
            source_image = image_pad(source_image, [(0, 0), (side_1, side_2), (0, 0)], mode='constant', constant_values=(0, 0))
        else:
            width = int(256*width / height)
            height = 256
            source_image = resize(source_image, (width, height))[..., :3]
            remaining = 256-width
            side_1 = int(remaining/2)
            side_2 = int(remaining - side_1)
            source_image = image_pad(source_image, [(side_1, side_2), (0, 0), (0, 0)], mode='constant', constant_values=(0, 0))
    elif args.image_resize == 'stretch':
        print("Mode: Stretch")
        source_image = resize(source_image, (256, 256))[..., :3]
    elif args.image_resize == 'crop':
        print("Mode: Crop")
        width, height = source_image.shape[:2]
        if width < height:
            height = int(256*height / width)
            width = 256
            source_image = resize(source_image, (width, height))[..., :3]
            x_center, y_center = 128, height//2
            source_image = source_image[:, y_center-128:y_center+128, :]
        else:
            width = int(256*width / height)
            height = 256
            source_image = resize(source_image, (width, height))[..., :3]
            x_center, y_center = width//2, 128
            source_image = source_image[x_center-128:x_center+128, :, :]
    else:
        raise NotImplementedError("Invalid Image Resize Mode")


if source_video.size != [256, 256]:
    print("Resizing Video to 256x256 with ", end = '')
    if args.video_resize == 'fill':
        print("Mode: Fill")
        width, height = source_video.size
        if width > height:
            height = int(256*height / width)
            width = 256
            source_video = movie_resize(source_video, (width, height))
            remaining = 256-height
            side_1 = int(remaining/2)
            side_2 = int(remaining - side_1)
            source_video = movie_margin(source_video, top=side_1, bottom=side_2, color=(0, 0, 0))
        else:
            width = int(256*width / height)
            height = 256
            source_video = movie_resize(source_video, (width, height))
            remaining = 256-width
            side_1 = int(remaining/2)
            side_2 = int(remaining - side_1)
            source_video = movie_margin(source_video, left=side_1, right=side_2, color=(0, 0, 0))
    elif args.video_resize == 'stretch':
        print("Mode: Stretch")
        # driving_video = [resize(frame, (256, 256))[..., :3] for frame in source_video.iter_frames()]
        source_video = movie_resize(source_video, (256, 256))
    elif args.video_resize == 'crop':
        print("Mode: Crop")
        width, height = source_video.size
        if width < height:
            height = int(256*height / width)
            width = 256
            source_video = movie_resize(source_video, (width, height))
            x_center, y_center = 128, height//2
        else:
            width = int(256*width / height)
            height = 256
            source_video = movie_resize(source_video, (width, height))
            x_center, y_center = width//2, 128
        source_video = movie_crop(source_video, x_center=x_center, y_center=y_center, width=256, height=256)
    else:
        raise NotImplementedError("Invalid Video Resize Mode")

driving_video = [(frame/255) for frame in source_video.iter_frames()]
print()


print("Generating Video")
predictions = make_animation(source_image, driving_video, generator, kp_detector, **options)
print()


def make_frame(t):
        try:
            x = predictions[int(len(predictions)/source_duration*t)]
        except:
            x = predictions[-1]

        return (x*255).astype(np.uint8)


output_clip = VideoClip(make_frame, duration=source_duration)
output_clip = output_clip.set_fps(source_fps)
output_clip = output_clip.set_audio(source_audio)


print("Saving Video...")
output_clip.write_videofile(output_video_path, logger=None, verbose=False, **codecs[args.codec])

print("Video saved to", output_video_path)
print()

if args.stack:
    print("Saving Side by Side Video")
    stack_clip = clips_array([[output_clip.margin(right=10), source_video]])
    stack_path = output_video_path.rsplit('.', 1)[0] + '_stacked.mp4'
    stack_clip.write_videofile(stack_path, logger=None, verbose=False, **codecs[args.codec])
    print("Stacked Video saved to", stack_path)
    stack_clip.close()

output_clip.close()
source_video.close()