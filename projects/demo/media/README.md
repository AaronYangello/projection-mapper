# Optional example media

`sintel-trailer.mp4` is the unmodified trailer used for native playback testing. It is downloaded
locally, excluded from Git, and is not fetched automatically by the application.

- **Credit:** Sintel © Blender Foundation · [Sintel project](https://durian.blender.org/)
- **License:** [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/)
- **License statement:** [Blender Foundation sharing page](https://durian.blender.org/sharing/)
- **Example host:** [W3C HTML video example](https://www.w3.org/2010/05/video/mediaevents.html)
- **File source:** [W3C Sintel trailer](https://media.w3.org/2010/05/sintel/trailer.mp4)
- **SHA-256:** `b670602fa00934ca27c4351bb0efe7ea7a07fae57284e44226025eeed7c51254`
- **Measured file:** 4,372,373 bytes, 854×480, H.264, 24 fps, 52.208 seconds.
- **Changes:** none to the downloaded file. Playback ignores audio; crop/fit changes are runtime transforms.

From the repository root:

```sh
.venv/bin/python scripts/download_sample.py
```

The demo configuration includes this source. If the optional file is absent, it is skipped with
a visible warning and the remaining color scenes continue. You can remove its scene entry for
a completely media-free demo. Add your own local videos/images here and use Media → Scan.
