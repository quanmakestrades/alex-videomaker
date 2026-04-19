# ffmpeg reference

The exact ffmpeg commands videomaker runs, with explanations. Useful when debugging a
stitching failure or when you want to run a one-off variant by hand.

## Per-scene segment build

For each scene, build a short MP4 from a still image + narration MP3:

```
ffmpeg -y -loglevel error \
  -loop 1 -i <image.png> \
  -i <audio.mp3> \
  -c:v libx264 \
  -tune stillimage \
  -pix_fmt yuv420p \
  -crf 20 \
  -r 30 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1" \
  -c:a aac -b:a 192k \
  -shortest \
  -movflags +faststart \
  <segment.mp4>
```

Explanation:
- `-loop 1 -i image.png` — loop the still image indefinitely.
- `-i audio.mp3` — feed the MP3 as the second input.
- `-tune stillimage` — x264 preset optimized for single-image video (tiny files, low CPU).
- `-pix_fmt yuv420p` — required for wide player compatibility (YouTube, QuickTime).
- `-vf scale=... pad=...` — letterbox. Keeps the image's aspect ratio, pads with black to 1920x1080.
- `-shortest` — stop encoding when the shortest input (the audio) ends. This is what makes the scene duration match the narration.
- `-movflags +faststart` — moves the moov atom to the start of the file so browsers can stream it.
- `-crf 20` — quality/size knob. 18 = near-lossless big files; 23 = good quality smaller; 28 = visible compression, ~30% smaller. Default 20 is a good balance.

## Concat

After all segments exist, concat via the concat demuxer:

```
# list.txt:
#   file 'scene_001.mp4'
#   file 'scene_002.mp4'
#   ...

ffmpeg -y -loglevel error \
  -f concat -safe 0 \
  -i list.txt \
  -c copy \
  -movflags +faststart \
  final.mp4
```

`-c copy` = stream copy (no re-encoding) = instant. Works because all segments were built
with identical codec params. If it fails (usually when one segment has slightly different
timestamps), the pipeline falls back to a re-encode:

```
ffmpeg -y -loglevel error \
  -f concat -safe 0 \
  -i list.txt \
  -c:v libx264 -crf 20 \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  final.mp4
```

## ffprobe — measuring audio duration

The pipeline uses ffprobe to measure each MP3's duration so it can timestamp the manifest:

```
ffprobe -v error \
  -show_entries format=duration \
  -of json \
  <audio.mp3>
```

Returns `{"format": {"duration": "5.234000"}}`. Parsed as a float.

## Manual crossfades (not yet in pipeline)

If you want 100ms crossfades between scenes, the concat demuxer won't do that — you'd need
a filter_complex chain. Placeholder for v0.2. Rough shape:

```
ffmpeg -y \
  -i seg1.mp4 -i seg2.mp4 -i seg3.mp4 \
  -filter_complex "[0][1]xfade=transition=fade:duration=0.1:offset=$DUR_1[v01]; \
                   [v01][2]xfade=transition=fade:duration=0.1:offset=$DUR_1_2[v]; \
                   [0:a][1:a]acrossfade=d=0.1[a01]; \
                   [a01][2:a]acrossfade=d=0.1[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -crf 20 -c:a aac -b:a 192k \
  final.mp4
```

The offsets have to be computed from probed durations. This gets messy at 200 scenes and
is why the MVP just does hard cuts. Hard cuts actually work fine for the reference style —
educational channels use them liberally.

## Background music bed (not yet in pipeline)

To add a ducked music bed, mix after final stitch:

```
ffmpeg -y \
  -i final.mp4 \
  -i bgm.mp3 \
  -filter_complex "[1:a]volume=0.15[bgm]; \
                   [0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]" \
  -map 0:v -map "[a]" \
  -c:v copy -c:a aac -b:a 192k \
  final_with_bgm.mp4
```

## Codec/quality presets

If CRF 20 at 1080p gives files too large for email:

| CRF | ~Size for 15 min | Quality |
|-----|------------------|---------|
| 18  | 250–400 MB       | near-lossless |
| 20  | 150–220 MB       | visually transparent |
| 23  | 80–130 MB        | good, default YouTube re-encode source |
| 26  | 45–75 MB         | visible compression, fine on phones |
| 28  | 30–50 MB         | noticeable compression |

Edit `video.crf` in `~/.videomaker/config.yaml`.
