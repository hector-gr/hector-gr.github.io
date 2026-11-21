# ReImaGin explainer video source

This is the source for `reimagin/assets/video/reimagin-explainer.mp4`.
Python draws each frame using Pillow and streams it to FFmpeg to encode the MP4.

## Requirements

- Python 3 with Pillow: `python3 -m pip install -r requirements.txt`
- FFmpeg installed and available on PATH (macOS: `brew install ffmpeg`)
- macOS system fonts: Iowan Old Style and Andale Mono. For other platforms,
  update the `IOW` and `AND` font paths in `render.py`.

## Render

From the repository root:

```sh
cd reimagin/video-source
python3 -m pip install -r requirements.txt
python3 render.py
```

The output is `reimagin_explainer_v2.mp4` (1920 × 1080, 30 fps).
The renderer overwrites that output file when run again.

## Edit

- `render.py`: scenes, animation, typography, colors, and timing.
- `_SEQ` near the bottom of `render.py`: scene order and durations.
- `pptx/ppt/media/`: source images and figures extracted from the slides.

Generated videos are ignored here. The website's existing MP4 is stored separately
in `reimagin/assets/video/`.
