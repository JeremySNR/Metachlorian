# Extra eval footage - sources and licences

Collected 2026-10-04 for the Metachlorian gold set. Every file below was downloaded from the URL shown, inspected (frame sheets extracted with ffmpeg and viewed), and probed with ffprobe. Derived files (trims, re-encodes, concatenations, retimes) say exactly what was done.

**Licence flags:** `OK` = permissive (CC0 / CC BY / ODbL); `CHECK` = usable for internal eval but read the note before redistributing; `LOCAL-ONLY` = licence unclear/conflicting - local eval only, do not redistribute.

## Licence texts quoted

- **shotstack** - CC0 1.0. Repo README: "All assets are licensed using the Creative Commons Zero license which means you are free to use them how you like without any costs or attribution required." LICENSE file: "CC0 1.0 Universal".

- **tos** - CC BY 3.0. sitkevij/test-media README: "Tears of Steel media Adapted under Creative Commons Attribution 3.0 license. (CC) Blender Foundation | mango.blender.org". andreasbotsikas/DemoVideos Readme: "The proceedings and results of the Mango Open Movie project are being licensed under the Creative Commons Attribution 3.0 license."

- **netflix_ccby** - CC BY 4.0 (current); see note. Title folder licence file (e.g. s3://download.opencontent.netflix.com/Meridian/creative-commons-attribution-4-intl-public-license.txt): "Our open source content is available under the Creative Commons Attribution 4.0 International Public License." NOTE: the older per-title notice TechblogAssets/Meridian/meridian_license.txt (Nov 2016) says "licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License". Netflix has since relicensed Open Content to CC BY 4.0 (opencontent.netflix.com states CC BY 4.0), but the old NC-ND notice is still in the bucket. Treat as CC BY 4.0 with that caveat.

- **netflix_testcond** - CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed. Netflix_test_conditions/Chimera_copyright.txt (Dec 2015, text actually headed "ElFuente digital video content"): "This video sequence is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License." The title folders Chimera/ and ElFuente/ now each carry creative-commons-attribution-4-intl-public-license.txt ("Our open source content is available under the Creative Commons Attribution 4.0 International Public License."). Licence status conflicting - local eval only, do not redistribute until confirmed CC BY 4.0.

- **ugc** - CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code). YouTube UGC dataset, gs://ugc-dataset/ATTRIBUTION: "<clip> is an audio-removed excerpt from '<title>' by '<creator>' licensed under CC BY 4.0". gs://ugc-dataset/LICENSE contains the Creative Commons Attribution 3.0 Unported legal code. Original uploads were YouTube Creative Commons (CC BY) videos.

- **cremad** - ODbL 1.0 / DbCL 1.0. CREMA-D LICENSE.txt: "This Crowd-sourced Emotional Mutimodal Actors Dataset (CREMA-D) is made available under the Open Database License: http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual contents of the database are licensed under the Database Contents License: http://opendatacommons.org/licenses/dbcl/1.0/"

- **mdn** - CC0 1.0. mdn/interactive-examples LICENSE: "CC0 1.0 Universal" (whole repo); files live under live-examples/media/cc0-videos/ and media/examples/.

- **pexels** - Pexels License (not CC; free use, no attribution required) - verify per clip. Vaticay/cerebrum public/assets/cinematic/manifest.json lists each clip with "license": "Pexels", "license_url": "https://www.pexels.com/license/" and the original Pexels page. Files are the repo's 720p re-encodes (CRF 20, silent, <=15 s). The cerebrum repo itself has no LICENSE file. Pexels License permits free use/modification without attribution but forbids selling unaltered copies and implying endorsement. Not a CC licence - fine for internal eval; do not redistribute as a dataset without checking.


## Files

### cremad_10speakers_concat.en.srt

- URL: (generated)
- Licence: ODbL 1.0 / DbCL 1.0 [OK] (see `cremad` above)
- Attribution: as above
- Shows: Ground-truth transcript for the concatenated CREMA-D clip (one cue per speaker, scripted sentence).

### cremad_10speakers_concat.mp4

- URL: https://media.githubusercontent.com/media/CheyneyComputerScience/CREMA-D/master/VideoFlash/<ID>.flv
- Licence: ODbL 1.0 / DbCL 1.0 [OK] (see `cremad` above)
- Attribution: CREMA-D: Cao H, Cooper DG, Keutmann MK, Gur RC, Nenkova A, Verma R. (2014) Crowd-sourced Emotional Multimodal Actors Dataset. github.com/CheyneyComputerScience/CREMA-D
- Probe: 25.76 s, video h264 480x360 @ 29.97 fps, audio aac 1ch, 2.3 MB
- Shows: 10 consecutive talking-head clips (10 different actors, mixed ages/sexes) in front of a green screen, each speaking one scripted English sentence with an emotion; hard cuts between speakers. 480x360, 29.97 fps, mono audio.
- Notes: Derived by us: concatenated 1001_DFA_ANG_XX, 1012_IEO_HAP_HI, 1023_TIE_NEU_XX, 1034_IOM_NEU_XX, 1045_IWW_FEA_XX, 1056_TAI_DIS_XX, 1067_MTI_NEU_XX, 1078_IWL_HAP_XX, 1089_ITH_ANG_XX, 1091_WSI_NEU_XX (VP6 FLV) and re-encoded to H.264/AAC. Exact spoken sentences with timings in cremad_10speakers_concat.en.srt (sentence text from the CREMA-D sentence codes).

### mdn_cc0_flower.mp4

- URL: https://raw.githubusercontent.com/mdn/interactive-examples/main/live-examples/media/cc0-videos/flower.mp4
- Licence: CC0 1.0 [OK] (see `mdn` above)
- Attribution: MDN Web Docs (mdn/interactive-examples), CC0
- Probe: 5.05 s, video h264 960x540 @ 29.97 fps, audio aac 2ch, 1.1 MB
- Shows: Time-lapse macro of a red flower bud opening among purple-edged leaves, shallow depth of field, 5 s, 960x540, silent audio track.

### mdn_cc0_friday.mp4

- URL: https://raw.githubusercontent.com/mdn/interactive-examples/main/live-examples/media/cc0-videos/friday.mp4
- Licence: CC0 1.0 [OK] (see `mdn` above)
- Attribution: MDN Web Docs (mdn/interactive-examples), CC0
- Probe: 6.17 s, video h264 640x480 @ 30.0 fps, audio aac 2ch, 0.5 MB
- Shows: 6 s black-and-white 1940s film clip (appears to be from 'His Girl Friday', 1940, US public domain): women at a switchboard/desk in a newsroom, one in a hat leaning on the counter; English dialogue audio.
- Notes: Identification of the film is our inference from the filename and image; MDN publishes it in its cc0-videos folder.

### mdn_stream-of-water.mp4

- URL: https://raw.githubusercontent.com/mdn/interactive-examples/main/live-examples/media/examples/stream-of-water.mp4
- Licence: CC0 1.0 [OK] (see `mdn` above)
- Attribution: MDN Web Docs (mdn/interactive-examples), CC0
- Probe: 3.16 s, video h264 480x360 @ 29.97 fps, audio aac 1ch, 0.3 MB
- Shows: 3 s static shot of a small stream flowing between boulders on dry ground, 480x360.

### netflix_chimera_aerial_drone.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/Aerial_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 19.95 s, video h264 1920x1080 @ 29.97 fps, audio none, 46.0 MB
- Shows: Chimera 'Aerial': starts on a group of people with a drone operator on a hillside by a house, then the drone takes off - rising aerial over the house and scrubby hillside/canyon. Drone/aerial with camera rising.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 29.97 fps with -c copy. No audio.

### netflix_chimera_driving_pov.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/DrivingPOV_1920x1080_QP24.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 17.95 s, video h264 1920x1080 @ 29.97 fps, audio none, 15.7 MB
- Shows: Chimera 'DrivingPOV': forward car-mounted POV along a palm-lined coastal avenue, crosswalk markings, oncoming car. Travel B-roll / tracking.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 29.97 fps with -c copy. No audio.

### netflix_chimera_pier_seaside.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/PierSeaside_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 9.94 s, video h264 1920x1080 @ 29.97 fps, audio none, 15.7 MB
- Shows: Chimera 'PierSeaside': Santa Monica-style pier building on stilts over the ocean, slow pan/drift ending on open sea and surf. Water/ocean, daylight.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 29.97 fps with -c copy. No audio.

### netflix_chimera_rollercoaster.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/RollerCoasterPassenger_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 14.95 s, video h264 1920x1080 @ 29.97 fps, audio none, 25.3 MB
- Shows: Chimera 'RollerCoasterPassengers': front-mounted camera on a yellow roller-coaster car with smiling passengers, pulling out of the station on a seaside pier. Fast motion, people.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 29.97 fps with -c copy. No audio.

### netflix_chimera_wind_nature.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/WindAndNature_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 9.94 s, video h264 1920x1080 @ 29.97 fps, audio none, 10.7 MB
- Shows: Chimera 'WindAndNature': locked-off shot of a dense field of thin metal wind-chime/spinner poles in front of a tree, fine detail swaying in wind.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 29.97 fps with -c copy. No audio.

### netflix_elfuente_boat_60p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/Boat_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 4.92 s, video h264 1920x1080 @ 59.94 fps, audio none, 18.3 MB
- Shows: El Fuente 'Boat': low-angle shot of a painted Xochimilco trajinera sign ('BIENVENIDOS') gliding past trees against the sky, 59.94 fps.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 59.94 fps with -c copy. No audio.

### netflix_elfuente_boxing_60p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/BoxingPractice_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 4.16 s, video h264 1920x1080 @ 59.94 fps, audio none, 6.3 MB
- Shows: El Fuente 'BoxingPractice': boxing gym with hanging heavy bags, boxers sparring/shadow-boxing, ring in background, 59.94 fps (sports).
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 59.94 fps with -c copy. No audio.

### netflix_elfuente_boxing_slowmo2.5x_conformed24p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/BoxingPractice_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - El Fuente test content
- Probe: 10.49 s, video h264 1920x1080 @ 23.976 fps, audio none, 6.3 MB
- Shows: Same boxing-gym shot conformed from 59.94 to 23.976 fps -> 2.5x slow motion (overcrank-style, no frame interpolation).
- Notes: Derived by us: remuxed with -r 24000/1001 -c copy, i.e. the true 59.94p frames retimed to 23.976p. This is how real slow motion is delivered, but it is our conform, not a camera-original slow-mo file.

### netflix_elfuente_crosswalk_60p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/Crosswalk_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 4.92 s, video h264 1920x1080 @ 59.94 fps, audio none, 7.7 MB
- Shows: El Fuente 'Crosswalk': dense crowd crossing a city street toward camera, shallow depth of field, faces, 59.94 fps (handheld street scene).
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 59.94 fps with -c copy. No audio.

### netflix_elfuente_foodmarket2_60p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/FoodMarket2_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 4.92 s, video h264 1920x1080 @ 59.94 fps, audio none, 12.0 MB
- Shows: El Fuente 'FoodMarket2': high-angle crane/jib move over produce market stalls with sacks of vegetables, crowds, 59.94 fps.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 59.94 fps with -c copy. No audio.

### netflix_elfuente_foodmarket_60p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/FoodMarket_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 6.79 s, video h264 1920x1080 @ 59.94 fps, audio none, 20.1 MB
- Shows: El Fuente 'FoodMarket': busy Mexico City wholesale flower/produce market at dawn, porters carrying bundles past camera, handheld/tracking, 59.94 fps.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 59.94 fps with -c copy. No audio.

### netflix_elfuente_narrator_60p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/Narrator_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 4.92 s, video h264 1920x1080 @ 59.94 fps, audio none, 4.3 MB
- Shows: El Fuente 'Narrator': man in suit and scarf walking toward camera on a tree-lined plaza with people behind (no audio), 59.94 fps.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 59.94 fps with -c copy. No audio.

### netflix_elfuente_tango_60p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/Tango_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - Chimera / El Fuente test content (Netflix Open Content)
- Probe: 4.82 s, video h264 1920x1080 @ 59.94 fps, audio none, 8.9 MB
- Shows: El Fuente 'Tango': crowded outdoor dance, woman in pink dress and man in pink suit/fedora dancing, close/medium shots, 59.94 fps.
- Notes: Raw H.264 elementary stream (x264 QP16/QP24 test-condition encode of the 4K master, 1080p) remuxed by us to MP4 at 59.94 fps with -c copy. No audio.

### netflix_elfuente_tango_slowmo2.5x_conformed24p.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Netflix_test_conditions/encodes/x264/Tango_1920x1080_QP16.264
- Licence: CC BY 4.0 (current) vs CC BY-NC-ND 4.0 (old notice) - conflicting; local eval only until confirmed [LOCAL-ONLY] (see `netflix_testcond` above)
- Attribution: Netflix, Inc. - El Fuente test content
- Probe: 12.15 s, video h264 1920x1080 @ 23.976 fps, audio none, 8.9 MB
- Shows: Same tango crowd shot conformed from 59.94 to 23.976 fps -> 2.5x slow motion.
- Notes: Derived by us: remuxed with -r 24000/1001 -c copy, i.e. the true 59.94p frames retimed to 23.976p. This is how real slow motion is delivered, but it is our conform, not a camera-original slow-mo file.

### netflix_meridian_0000-0200_1080p60.en.srt

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/Meridian/subtitles/STL/Meridian_en_CC.stl
- Licence: CC BY 4.0 (current); see note [CHECK] (see `netflix_ccby` above)
- Attribution: Netflix, Inc.
- Shows: English closed captions (SDH) for the Meridian excerpt, converted EBU-STL -> SRT.

### netflix_meridian_0000-0200_1080p60.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/TechblogAssets/Meridian/encodes/Meridian_3840x2160_5994fps_SDR.mp4
- Licence: CC BY 4.0 (current); see note [CHECK] (see `netflix_ccby` above)
- Attribution: Meridian (2016) - Netflix, Inc. Netflix Open Content, CC BY 4.0
- Probe: 120.00 s, video h264 1920x1080 @ 59.94 fps, audio aac 2ch, 52.3 MB
- Shows: First 2:00 of Meridian, a 1947-set film-noir short: LA street establishing shots with 'Los Angeles 1947' / 'Meridian' titles, then two detectives in an LAPD office in shot/reverse-shot dialogue (English), low-key lighting, venetian-blind shadows, cigarette smoke.
- Notes: Derived by us: first 120 s, scaled 3840x2160 -> 1920x1080, x264 CRF 21 (59.94 fps kept), AAC 160k. English captions in netflix_meridian_0000-0200_1080p60.en.srt, converted from Meridian/subtitles/STL/Meridian_en_CC.stl (EBU STL, 25 fps timecodes); alignment with this encode not verified (spot check suggests close).

### netflix_sparks_0000-0200_1080p60.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/TechblogAssets/Sparks/encodes/Sparks_4096x2160_5994fps_SDR.mp4
- Licence: CC BY 4.0 (current); see note [CHECK] (see `netflix_ccby` above)
- Attribution: Sparks (2017) - Netflix, Inc. Netflix Open Content, CC BY 4.0
- Probe: 120.00 s, video h264 1920x1012 @ 59.94 fps, audio aac 2ch, 92.3 MB
- Shows: First 2:00 of Sparks: pre-dawn treeline silhouette, then ironworkers at a construction site, grinder/welding sparks close-ups, silhouettes against valley, crew conversation; finished edit with many cuts and a dawn-to-day time-of-day arc.
- Notes: Derived by us: first 120 s, scaled to 1920 wide, x264 CRF 21, 59.94 fps, AAC 160k.

### netflix_sparks_4k60_excerpt.mp4

- URL: https://s3.amazonaws.com/download.opencontent.netflix.com/TechblogAssets/Sparks/encodes/Sparks_4096x2160_5994fps_SDR.mp4
- Licence: CC BY 4.0 (current); see note [CHECK] (see `netflix_ccby` above)
- Attribution: Sparks (2017) - Netflix, Inc. Netflix Open Content, CC BY 4.0
- Probe: 15.07 s, video h264 4096x2160 @ 59.94 fps, audio aac 2ch, 26.9 MB
- Shows: 15 s native 4096x2160 59.94 fps excerpt (stream copy from 1:00): ironworkers on a steel-frame construction site, red stairs, welder in a flip-up mask; several cuts.
- Notes: Cut by us with -ss 60 -t 15 -c copy (keyframe-aligned start).

### pexels_via_cerebrum_science-03.mp4

- URL: https://raw.githubusercontent.com/Vaticay/cerebrum/main/public/assets/cinematic/science-03.mp4
- Licence: Pexels License (not CC; free use, no attribution required) - verify per clip [CHECK] (see `pexels` above)
- Attribution: David Roberts on Pexels - original: https://www.pexels.com/video/time-lapse-of-seedlings-8522207/ (manifest title: 'Seedling growth timelapse')
- Probe: 12.88 s, video h264 1280x720 @ 24.0 fps, audio none, 1.3 MB
- Shows: Time-lapse of seedlings growing in dark soil, low macro angle (timelapse).
- Notes: Downloaded as-is: a 720p silent H.264 re-encode/excerpt made by the cerebrum repo (see its manifest 'modifications' field); the original-resolution file is on Pexels (blocked from this sandbox).

### pexels_via_cerebrum_science-11.mp4

- URL: https://raw.githubusercontent.com/Vaticay/cerebrum/main/public/assets/cinematic/science-11.mp4
- Licence: Pexels License (not CC; free use, no attribution required) - verify per clip [CHECK] (see `pexels` above)
- Attribution: Mikhail Nilov on Pexels - original: https://www.pexels.com/video/drone-footage-of-glaciers-at-greenland-8318618/ (manifest title: 'Greenland icebergs')
- Probe: 11.29 s, video h264 1280x720 @ 24.0 fps, audio none, 2.4 MB
- Shows: Drone footage gliding over Greenland sea ice / icebergs and dark open water (aerial, nature).
- Notes: Downloaded as-is: a 720p silent H.264 re-encode/excerpt made by the cerebrum repo (see its manifest 'modifications' field); the original-resolution file is on Pexels (blocked from this sandbox).

### pexels_via_cerebrum_science-28.mp4

- URL: https://raw.githubusercontent.com/Vaticay/cerebrum/main/public/assets/cinematic/science-28.mp4
- Licence: Pexels License (not CC; free use, no attribution required) - verify per clip [CHECK] (see `pexels` above)
- Attribution: Hao Le on Pexels - original: https://www.pexels.com/video/macro-shot-of-butterfly-on-a-flower-38759167/ (manifest title: 'Butterfly feeding on a flower')
- Probe: 10.00 s, video h264 406x720 @ 24.0 fps, audio none, 0.5 MB
- Shows: Vertical (406x720) macro of a monarch butterfly feeding on a purple coneflower (wildlife/macro, vertical).
- Notes: Downloaded as-is: a 720p silent H.264 re-encode/excerpt made by the cerebrum repo (see its manifest 'modifications' field); the original-resolution file is on Pexels (blocked from this sandbox).

### pexels_via_cerebrum_science-31.mp4

- URL: https://raw.githubusercontent.com/Vaticay/cerebrum/main/public/assets/cinematic/science-31.mp4
- Licence: Pexels License (not CC; free use, no attribution required) - verify per clip [CHECK] (see `pexels` above)
- Attribution: Peter Fowler on Pexels - original: https://www.pexels.com/video/ocean-waves-video-1093652/ (manifest title: 'Ocean waves at rocks')
- Probe: 10.00 s, video h264 1280x720 @ 24.0 fps, audio none, 2.7 MB
- Shows: Low drone/handheld shot over ocean waves breaking at sunset, rocks in silhouette (water/ocean, golden hour).
- Notes: Downloaded as-is: a 720p silent H.264 re-encode/excerpt made by the cerebrum repo (see its manifest 'modifications' field); the original-resolution file is on Pexels (blocked from this sandbox).

### pexels_via_cerebrum_science-33.mp4

- URL: https://raw.githubusercontent.com/Vaticay/cerebrum/main/public/assets/cinematic/science-33.mp4
- Licence: Pexels License (not CC; free use, no attribution required) - verify per clip [CHECK] (see `pexels` above)
- Attribution: Anoop A Nair on Pexels - original: https://www.pexels.com/video/lava-in-volcano-in-slow-motion-13438865/ (manifest title: 'Volcanic lava in slow motion')
- Probe: 10.00 s, video h264 1280x720 @ 24.0 fps, audio none, 2.9 MB
- Shows: Slow-motion close shot of lava fountaining and splashing at night (slow motion, night).
- Notes: Downloaded as-is: a 720p silent H.264 re-encode/excerpt made by the cerebrum repo (see its manifest 'modifications' field); the original-resolution file is on Pexels (blocked from this sandbox).

### pexels_via_cerebrum_science-35.mp4

- URL: https://raw.githubusercontent.com/Vaticay/cerebrum/main/public/assets/cinematic/science-35.mp4
- Licence: Pexels License (not CC; free use, no attribution required) - verify per clip [CHECK] (see `pexels` above)
- Attribution: T Honkamies on Pexels - original: https://www.pexels.com/video/northern-lights-timelapse-28492331/ (manifest title: 'Northern lights timelapse')
- Probe: 14.00 s, video h264 1280x720 @ 24.0 fps, audio none, 3.6 MB
- Shows: Northern-lights (aurora borealis) time-lapse over a dark treeline, stars (night sky timelapse).
- Notes: Downloaded as-is: a 720p silent H.264 re-encode/excerpt made by the cerebrum repo (see its manifest 'modifications' field); the original-resolution file is on Pexels (blocked from this sandbox).

### pexels_via_cerebrum_science-36.mp4

- URL: https://raw.githubusercontent.com/Vaticay/cerebrum/main/public/assets/cinematic/science-36.mp4
- Licence: Pexels License (not CC; free use, no attribution required) - verify per clip [CHECK] (see `pexels` above)
- Attribution: Aaron Burden on Pexels - original: https://www.pexels.com/video/a-macro-footage-of-a-water-bubble-slowly-freezing-on-a-cold-winter-s-day-2478688/ (manifest title: 'Soap bubble freezing, macro')
- Probe: 14.01 s, video h264 1280x720 @ 29.97 fps, audio none, 1.7 MB
- Shows: Macro of a soap bubble freezing into ice-crystal fern patterns against low sun (macro, slow process).
- Notes: Downloaded as-is: a 720p silent H.264 re-encode/excerpt made by the cerebrum repo (see its manifest 'modifications' field); the original-resolution file is on Pexels (blocked from this sandbox).

### shotstack_h1080_w1920_f30_a16-9_r0.mp4

- URL: https://raw.githubusercontent.com/shotstack/test-media/main/orientation/h1080_w1920_f30_a16-9_r0.mp4
- Licence: CC0 1.0 [OK] (see `shotstack` above)
- Attribution: Jeff Shillitto (@jeffski), via shotstack/test-media
- Probe: 11.50 s, video h264 1920x1080 @ 30.0 fps, audio aac 2ch, 20.7 MB
- Shows: Phone (Samsung Galaxy S9) handheld-on-tripod wide shot of a surf beach / rocky headland, turquoise water, surfers; landscape, rotation 0.
- Notes: Rotation-metadata test set; all four are the same location.

### shotstack_h1080_w1920_f30_a16-9_r180.mp4

- URL: https://raw.githubusercontent.com/shotstack/test-media/main/orientation/h1080_w1920_f30_a16-9_r180.mp4
- Licence: CC0 1.0 [OK] (see `shotstack` above)
- Attribution: Jeff Shillitto (@jeffski), via shotstack/test-media
- Probe: 11.83 s, video h264 1920x1080 @ 30.0 fps, rotation -180, audio aac 2ch, 21.2 MB
- Shows: Same beach/surf scene, stored with rotation=180 metadata (phone held upside-down).
- Notes: Rotation-metadata test set; all four are the same location.

### shotstack_h1920_w1080_f30_a9-16_r270.mp4

- URL: https://raw.githubusercontent.com/shotstack/test-media/main/orientation/h1920_w1080_f30_a9-16_r270.mp4
- Licence: CC0 1.0 [OK] (see `shotstack` above)
- Attribution: Jeff Shillitto (@jeffski), via shotstack/test-media
- Probe: 12.11 s, video h264 1920x1080 @ 30.0 fps, rotation 90, audio aac 2ch, 21.8 MB
- Shows: Vertical 9:16 phone video of the surf beach with rotation=270 metadata.
- Notes: Rotation-metadata test set; all four are the same location.

### shotstack_h1920_w1080_f30_a9-16_r90.mp4

- URL: https://raw.githubusercontent.com/shotstack/test-media/main/orientation/h1920_w1080_f30_a9-16_r90.mp4
- Licence: CC0 1.0 [OK] (see `shotstack` above)
- Attribution: Jeff Shillitto (@jeffski), via shotstack/test-media
- Probe: 10.96 s, video h264 1920x1080 @ 30.0 fps, rotation -90, audio aac 2ch, 19.6 MB
- Shows: Vertical 9:16 phone video of the surf beach (rotation=90 metadata) - vertical-video test.
- Notes: Rotation-metadata test set; all four are the same location.

### shotstack_scott-ko.mp4

- URL: https://raw.githubusercontent.com/shotstack/test-media/main/captioning/scott-ko.mp4
- Licence: CC0 1.0 [OK] (see `shotstack` above)
- Attribution: Scott Ko - www.scottko.com.au (@thescottko), via shotstack/test-media
- Probe: 25.88 s, video h264 1920x1080 @ 23.976 fps, audio aac 2ch, 33.5 MB
- Shows: Talking-head piece-to-camera: man in white shirt at a desk with monitors, medium shot, speaks English to camera (25 s, 24 fps). Transcript in shotstack_scott-ko.srt (from the repo).
- Notes: Best English-speech ground truth in the set.

### shotstack_scott-ko.srt

- URL: https://raw.githubusercontent.com/shotstack/test-media/main/captioning/transcript.srt
- Licence: CC0 1.0 [OK] (see `shotstack` above)
- Attribution: as above
- Shows: Human transcript (SRT) for shotstack_scott-ko.mp4.

### tears_of_steel_0000-0200_512x292.en.vtt

- URL: https://raw.githubusercontent.com/quasarframework/quasar-ui-qmediaplayer/dev/packages/docs/public/media/TearsOfSteel/TOS-en.vtt
- Licence: CC BY 3.0 [OK] (see `tos` above)
- Attribution: (CC) Blender Foundation | mango.blender.org
- Shows: Official English subtitles (cues < 120 s kept) for the 2-minute Tears of Steel excerpt.
- Notes: Cue timing matches the official film; verify alignment against this encode.

### tears_of_steel_0000-0200_512x292.mp4

- URL: https://raw.githubusercontent.com/andreasbotsikas/DemoVideos/master/tears_of_steel.mp4
- Licence: CC BY 3.0 [OK] (see `tos` above)
- Attribution: (CC) Blender Foundation | mango.blender.org - Tears of Steel (2012)
- Probe: 120.00 s, video h264 512x292 @ 23.999 fps, audio aac 2ch, 17.1 MB
- Shows: First 2:00 of the Tears of Steel short (live action + VFX sci-fi): opening VFX shots, '40 YEARS LATER' title, couple arguing on a bridge in English, wide establishing shots. Low-res 512x292 source.
- Notes: Trimmed by us with ffmpeg -t 120 -c copy from the full 12:14 film (repo file is 512x292). English subtitles in tears_of_steel_0000-0200_512x292.en.vtt.

### tos_clip_10s.mov

- URL: https://raw.githubusercontent.com/sitkevij/test-media/master/media/tos-8434k-h264-yuv420p-1920x800-24fps-aac-44100s.mov
- Licence: CC BY 3.0 [OK] (see `tos` above)
- Attribution: (CC) Blender Foundation | mango.blender.org - Tears of Steel
- Probe: 10.08 s, video h264 1920x800 @ 24.0 fps, audio aac 2ch, 11.2 MB
- Shows: 10.6 s 1920x800 excerpt of Tears of Steel: live-action actor on Amsterdam canal bridge beside a VFX robot, cut to close-ups of two scientists behind holographic screens (finished edit, several cuts, VFX).

### ugc_HDR_1080P-2d32_train_station_handheld.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/HDR_1080P-2d32_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: '松竹站隨手拍：捷運綠線試車與台鐵區間車發車' by rail02000 (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1920x1080 @ 30.0 fps, audio none, 15.0 MB
- Shows: Handheld walk on an elevated rail station: view over city blocks and elevated track, then train arriving at a platform (Taichung).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID HDR_1080P-2d32. Original YouTube title: '松竹站隨手拍：捷運綠線試車與台鐵區間車發車'. HDR/HLG colour tags were not preserved in the dataset's 8-bit H.264 version, so it displays as flat/log-like SDR.

### ugc_HDR_1080P-7825_night_concert_stage.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/HDR_1080P-7825_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: '台中爵士音樂節隨拍：18/10/19' by rail02000 (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 19.97 s, video h264 1920x1080 @ 30.0 fps, audio none, 12.6 MB
- Shows: Night outdoor jazz-festival stage: band under purple stage lights and truss, smoke, audience silhouettes in foreground (night, concert, static wide).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID HDR_1080P-7825. Original YouTube title: '台中爵士音樂節隨拍：18/10/19'. HDR/HLG colour tags were not preserved in the dataset's 8-bit H.264 version, so it displays as flat/log-like SDR.

### ugc_HDR_2160P-40ab_hlg_flat_snowy_river_town_4k.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/HDR_2160P-40ab_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'HLG GH5' by guelinator (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 3840x2160 @ 30.0 fps, audio none, 30.2 MB
- Shows: GH5 HLG footage (flat, washed-out look): desk close-up of a Nivea tin and pen, then a snowy river bank and a snowy small-town river channel with houses under grey sky.
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 16 Mb/s, no audio (source is audio-removed). Clip ID HDR_2160P-40ab. Original YouTube title: 'HLG GH5'. HDR/HLG colour tags were not preserved in the dataset's 8-bit H.264 version, so it displays as flat/log-like SDR.

### ugc_HDR_2160P-664d_lowlight_lobby_interior_4k.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/HDR_2160P-664d_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'New York vid 1' by Superphilman 2 (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 3840x2160 @ 30.0 fps, audio none, 41.4 MB
- Shows: Low-light interiors: dim Art-Deco lobby (Empire State Building style) with mural, dark exhibit wall, windows; heavy noise and underexposure (4K handheld).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 16 Mb/s, no audio (source is audio-removed). Clip ID HDR_2160P-664d. Original YouTube title: 'New York vid 1'. HDR/HLG colour tags were not preserved in the dataset's 8-bit H.264 version, so it displays as flat/log-like SDR.

### ugc_HDR_2160P-6eeb_hlg_flat_sunset_coast_4k.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/HDR_2160P-6eeb_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'P1045787 GH5s 4K24p ALL I 10bits 400Mbps ISO640 HLG' by popconet (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 16.00 s, video h264 4096x2160 @ 30.0 fps, audio none, 51.6 MB
- Shows: Locked-off dusk/sunrise shot of a rocky wooded headland and sea with a few lights, pink horizon; shot on GH5s in HLG so it looks flat/low-contrast (flat-profile test). Source clip is 16 s (last ~1 s goes black).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 25 Mb/s, no audio (source is audio-removed). Clip ID HDR_2160P-6eeb. Original YouTube title: 'P1045787 GH5s 4K24p ALL I 10bits 400Mbps ISO640 HLG'. HDR/HLG colour tags were not preserved in the dataset's 8-bit H.264 version, so it displays as flat/log-like SDR.

### ugc_HowTo_1080P-13aa_cooking_stovetop_topdown.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/HowTo_1080P-13aa_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Beyond the Cookbook #03 | Juicy Bear Burger & Amberseed Buns' by Mr. Sean (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 19.97 s, video h264 1920x1080 @ 30.0 fps, audio none, 17.9 MB
- Shows: Top-down cooking shot: hand pours honey into a small saucepan of butter on a gas stove, stirring with a red spatula; granite counter (food close-up).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID HowTo_1080P-13aa. Original YouTube title: 'Beyond the Cookbook #03 | Juicy Bear Burger & Amberseed Buns'.

### ugc_HowTo_360P-55e9_food_closeup_frying.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/HowTo_360P-55e9_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'How to make Chicken noodle soup Like a Boss - Cooking With Brian - Top Secret Recipes' by Brian Frazer (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 640x360 @ 30.0 fps, audio none, 3.8 MB
- Shows: Low-res cooking close-ups: chopped chicken pieces with a red-handled spatula, then broth simmering in a pot (food, 360p).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID HowTo_360P-55e9. Original YouTube title: 'How to make Chicken noodle soup Like a Boss - Cooking With Brian - Top Secret Recipes'.

### ugc_MusicVideo_1080P-0706_musicvideo_cuts_drone_highway.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/MusicVideo_1080P-0706_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Myniakal - Piranhas (Official Music Video)' by Liam Higgins (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1920x1080 @ 30.0 fps, audio none, 14.6 MB
- Shows: Music video: rapper performing under coloured club lights intercut with purple-graded drone shots of a motorway/forest; letterboxed, fast cuts.
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID MusicVideo_1080P-0706. Original YouTube title: 'Myniakal - Piranhas (Official Music Video)'.

### ugc_MusicVideo_1080P-2b2b_musicvideo_bw_concert_cuts.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/MusicVideo_1080P-2b2b_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Flying Over The Homeland - Eternity  ( Single 2015 ) Official video' by Flying Over The Homeland (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1920x1080 @ 30.0 fps, audio none, 13.4 MB
- Shows: Black-and-white rock music video: singer, drummer close-ups, crowd and stage with band logo, smoke; letterboxed, rapid cuts.
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID MusicVideo_1080P-2b2b. Original YouTube title: 'Flying Over The Homeland - Eternity  ( Single 2015 ) Official video'.

### ugc_NewsClip_1080P-06df_news_anchor_street_broll.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/NewsClip_1080P-06df_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Quays TV News - February 15th 2013' by Quays News (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 19.97 s, video h264 1920x1080 @ 30.0 fps, audio none, 14.6 MB
- Shows: Student TV news: anchor in suit at a studio desk, then street B-roll of a pedestrianised UK shopping street (Manchester-style, Harvey Nichols) with shoppers; '@QuaysNews' bug (news edit with cuts, no audio).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID NewsClip_1080P-06df. Original YouTube title: 'Quays TV News - February 15th 2013'.

### ugc_Sports_1080P-679d_volleyball_interviews_lowerthirds.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Sports_1080P-679d_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'BSU Volleyball Looking to Rise Up' by LPTV - Lakeland Public Television (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1920x1080 @ 30.0 fps, audio none, 15.5 MB
- Shows: College volleyball feature: coach and players interviewed in a gym (medium close-ups, lower-third name caption 'Julie Touchett'), B-roll of players (interview format, audio removed).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID Sports_1080P-679d. Original YouTube title: 'BSU Volleyball Looking to Rise Up'.

### ugc_Sports_2160P-3d85_soccer_elevated_4k.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Sports_2160P-3d85_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Boys 2004 Academy - SLSG Chelsea - 1 min in to First goal Against (0-1)' by PAO STL Videos (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 3840x2160 @ 30.0 fps, audio none, 41.6 MB
- Shows: Youth soccer match filmed from high above (drone/pole) - wide, then near-top-down views of players and a corner flag (sports, aerial, 4K).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 16 Mb/s, no audio (source is audio-removed). Clip ID Sports_2160P-3d85. Original YouTube title: 'Boys 2004 Academy - SLSG Chelsea - 1 min in to First goal Against (0-1)'.

### ugc_Sports_480P-3f50_skatepark_contest_crowd.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Sports_480P-3f50_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'O Marisquiño 18 - WCS Street: Clasif. Chicos RONDA 4' by O'Marisquiño (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 19.97 s, video h264 960x540 @ 30.0 fps, audio none, 8.9 MB
- Shows: Skateboarding contest: crowd in grandstand, then wide shot of a skatepark with a skater riding rails, seaside stands behind (sports, 480p, broadcast graphics).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID Sports_480P-3f50. Original YouTube title: 'O Marisquiño 18 - WCS Street: Clasif. Chicos RONDA 4'.

### ugc_VerticalVideo_1080P-1ac1_vertical_supermarket_walk.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/VerticalVideo_1080P-1ac1_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Vlog 2 ở Mỹ: Đi chợ Việt Nam " Hong Kong Food Market". - Tân KR' by Tan KR (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1080x1920 @ 30.0 fps, audio none, 20.8 MB
- Shows: Vertical 9:16 handheld walk-through of an Asian supermarket aisles, fast motion blur, fluorescent lighting.
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID VerticalVideo_1080P-1ac1. Original YouTube title: 'Vlog 2 ở Mỹ: Đi chợ Việt Nam " Hong Kong Food Market". - Tân KR'.

### ugc_VerticalVideo_1080P-3d96_vertical_pier_walk.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/VerticalVideo_1080P-3d96_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'TT Vlog: гуляем под дождем' by Tatiana Tolmacheva (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 10.00 s, video h264 1080x1920 @ 30.0 fps, audio none, 10.7 MB
- Shows: Vertical 9:16 handheld walk along a wet stone causeway toward a wooden windmill by the sea (Nessebar-style), overcast, people walking ahead; ends on black.
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID VerticalVideo_1080P-3d96. Original YouTube title: 'TT Vlog: гуляем под дождем'.

### ugc_Vlog_1080P-21f5_wildlife_warthogs_safari.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Vlog_1080P-21f5_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Tanzania Safari' by PowersToTravel (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1920x1080 @ 30.0 fps, audio none, 20.7 MB
- Shows: Safari: warthogs running through tall grass with motion blur, then a warthog rolling in mud (wildlife, fast pans).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID Vlog_1080P-21f5. Original YouTube title: 'Tanzania Safari'.

### ugc_Vlog_1080P-64b6_fisheye_motorbike_pov.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Vlog_1080P-64b6_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Motorradtour Südfrankreich 2018-09-22-006-b inj' by DraKuhla (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1088x1088 @ 30.0 fps, audio none, 20.7 MB
- Shows: Circular-fisheye motorbike helmet/handlebar POV on a mountain road through rock tunnels (southern France), date/time burn-in overlay.
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID Vlog_1080P-64b6. Original YouTube title: 'Motorradtour Südfrankreich 2018-09-22-006-b inj'.

### ugc_Vlog_1080P-7e8c_wildlife_hippos_water.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Vlog_1080P-7e8c_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Tanzania Safari' by PowersToTravel (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 1920x1080 @ 30.0 fps, audio none, 20.4 MB
- Shows: Safari: shaky telephoto shot of hippos surfacing in a grey river (wildlife, water, handheld).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 8 Mb/s, no audio (source is audio-removed). Clip ID Vlog_1080P-7e8c. Original YouTube title: 'Tanzania Safari'.

### ugc_Vlog_2160P-0577_drone_aerial_suburb_4k.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Vlog_2160P-0577_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Aerial Cinematography | AlexGV' by ~Vlogs by Alex~ (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 20.00 s, video h264 3840x2160 @ 30.0 fps, audio none, 64.5 MB
- Shows: Drone aerial: opens on a top-down field with 'Aerial Cinematography' title, then drone rises over a park and suburban red-roofed housing estate under overcast sky (4K, camera ascending/orbiting).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 25 Mb/s, no audio (source is audio-removed). Clip ID Vlog_2160P-0577. Original YouTube title: 'Aerial Cinematography | AlexGV'.

### ugc_Vlog_2160P-2b2d_hiking_pov_coast_sunset_4k.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Vlog_2160P-2b2d_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'Long Overdue - Komodo trip Vlog 2017 part 1' by Felix Huray (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 19.97 s, video h264 3840x2160 @ 30.0 fps, audio none, 41.1 MB
- Shows: Travel/hiking POV (GoPro-style): feet and dry grass on a hillside, turquoise bay below, then coastline and sea at sunset (Komodo trip).
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 16 Mb/s, no audio (source is audio-removed). Clip ID Vlog_2160P-2b2d. Original YouTube title: 'Long Overdue - Komodo trip Vlog 2017 part 1'.

### ugc_Vlog_2160P-5874_fashionweek_vlog_street_4k.mp4

- URL: https://storage.googleapis.com/ugc-dataset/original_videos_h264/Vlog_2160P-5874_crf_10_ss_00_t_20.0.mp4
- Licence: CC BY (per-clip CC BY 4.0 per ATTRIBUTION; bucket LICENSE is CC BY 3.0 Unported legal code) [OK] (see `ugc` above)
- Attribution: 'VLOG 2 | MILAN FASHIONWEEK' by Maria Jernov (YouTube, CC BY 4.0) - via YouTube UGC dataset (Google), audio removed
- Probe: 19.97 s, video h264 3840x2160 @ 30.0 fps, audio none, 41.3 MB
- Shows: Fashion-week vlog: woman talking to camera (selfie handheld) under an overpass, Milan street with cars and crowd, then crowded show venue and catwalk seating with 'Sportmax AW17' caption.
- Notes: Derived by us from the 20 s CRF-10 H.264 mezzanine: re-encoded with x264 CRF 20 (veryfast/fast), maxrate 16 Mb/s, no audio (source is audio-removed). Clip ID Vlog_2160P-5874. Original YouTube title: 'VLOG 2 | MILAN FASHIONWEEK'.


Total media size: 1.06 GB

## Coverage summary (what each requested category maps to)

| Category | Files |
|---|---|
| Drone / aerial | ugc_Vlog_2160P-0577 (suburb, 4K), netflix_chimera_aerial_drone (take-off + rising aerial), ugc_Sports_2160P-3d85 (soccer from above), pexels science-11 (sea ice), ugc_MusicVideo_1080P-0706 (drone motorway inserts) |
| Handheld street / travel B-roll | netflix_elfuente_crosswalk_60p, ugc_NewsClip_1080P-06df (street B-roll), ugc_HDR_1080P-2d32 (rail station), ugc_Vlog_2160P-5874 (Milan street), ugc_VerticalVideo_1080P-3d96, netflix_chimera_driving_pov, ugc_Vlog_1080P-64b6 (fisheye motorbike POV), ugc_Vlog_2160P-2b2d (hiking POV) |
| Food / cooking | ugc_HowTo_1080P-13aa (top-down stove), ugc_HowTo_360P-55e9 (frying close-ups), netflix_elfuente_foodmarket(_2)_60p (market) |
| Night / low light | ugc_HDR_1080P-7825 (night concert), ugc_HDR_2160P-664d (dim lobby), pexels science-35 (aurora), pexels science-33 (lava at night), ugc_HDR_2160P-6eeb (dusk) |
| Nature / wildlife | ugc_Vlog_1080P-7e8c (hippos), ugc_Vlog_1080P-21f5 (warthogs), pexels science-28 (butterfly), netflix_chimera_wind_nature, mdn_stream-of-water, mdn_cc0_flower |
| Water / ocean / beach | shotstack orientation set (surf beach), netflix_chimera_pier_seaside, pexels science-31 (waves at sunset), ugc_HDR_2160P-6eeb (sea headland), ugc_Vlog_2160P-2b2d (bay/coast) |
| English speech (with audio) | shotstack_scott-ko (+SRT), netflix_meridian_0000-0200 (+SRT), tears_of_steel_0000-0200 (+VTT), tos_clip_10s, cremad_10speakers_concat (+SRT), mdn_cc0_friday |
| Interviews / talking heads (visual only, audio removed) | ugc_Sports_1080P-679d (interviews with lower thirds), ugc_NewsClip_1080P-06df (anchor), ugc_Vlog_2160P-5874 (selfie vlog) |
| Timelapse | mdn_cc0_flower, pexels science-03 (seedlings), pexels science-35 (aurora) |
| Slow motion | pexels science-33 (lava, source slow-mo), netflix_elfuente_*_slowmo2.5x_conformed24p (our 60p->24p conform) |
| Sports | ugc_Sports_2160P-3d85 (soccer), ugc_Sports_480P-3f50 (skatepark), ugc_Sports_1080P-679d (volleyball), netflix_elfuente_boxing_60p, netflix_chimera_rollercoaster |
| Vertical 9:16 | shotstack_h1920_w1080_*_r90/_r270, ugc_VerticalVideo_1080P-3d96, ugc_VerticalVideo_1080P-1ac1, pexels science-28 (406x720) |
| Log / flat profile | ugc_HDR_2160P-40ab and ugc_HDR_2160P-6eeb (Panasonic GH5/GH5s HLG, shown untagged = flat). No true S-Log/V-Log source found. |
| 4K | ugc_*_2160P_* (7 files, 3840/4096x2160), netflix_sparks_4k60_excerpt (4096x2160 59.94p) |
| High frame rate | netflix_elfuente_*_60p (59.94), netflix_sparks_* (59.94), netflix_meridian_0000-0200_1080p60 (59.94) |
| Finished edits with many cuts | netflix_meridian_0000-0200, netflix_sparks_0000-0200, tears_of_steel_0000-0200, tos_clip_10s, ugc_MusicVideo_1080P-0706/-2b2b, ugc_NewsClip_1080P-06df |
| Raw single takes | Netflix Chimera/El Fuente test shots, shotstack orientation clips, most UGC vlog/HDR clips, mdn clips |
| Rotation metadata | shotstack_*_r90/_r180/_r270 |

Not found with a usable licence: true camera-original slow-motion (120/240 fps) files, true log (S-Log/V-Log/C-Log) footage, aerial city-at-night. LibriSpeech/Common Voice (audio only) were not needed because the clips above carry English speech.
