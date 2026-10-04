#!/usr/bin/env bash
# Builds the camera / codec / bit-depth test set used in eval/README.md ("Formats").
# usage: eval/formats/make_matrix.sh <out-dir>   then: metachlorian --data <lib> add <out-dir> && metachlorian --data <lib> process
# Note: Ubuntu 24.04's libx264 writes undecodable 10-bit 4:2:2 streams; the XAVC S-I sample needs a current FFmpeg build
# (e.g. BtbN/FFmpeg-Builds). Real camera files from that profile decode fine with FFmpeg 6.1.
set -euo pipefail
out=${1:?out dir}; mkdir -p "$out"; cd "$out"
SRC=(-f lavfi -i testsrc2=size=1280x720:rate=25:duration=4 -f lavfi -i sine=frequency=440:duration=4:sample_rate=48000)
mk(){ name=$1; shift; ffmpeg -hide_banner -v error -y "${SRC[@]}" "$@" -shortest "$name" && echo "ok   $name" || echo "FAIL $name"; }
PRE="scale=out_color_matrix=bt709:out_range=tv,format=yuv444p10le,setparams=colorspace=bt709:color_trc=bt709:color_primaries=bt709:range=tv"
mk xavc_hs_hevc_422_10bit_hlg.mp4 -vf "$PRE,zscale=t=linear,format=gbrpf32le,zscale=p=2020,zscale=t=arib-std-b67:m=2020_ncl:r=tv:npl=203,format=yuv422p10le" -c:v libx265 -x265-params log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc -c:a aac
mk xavc_si_h264_422_10bit_intra.mp4 -vf scale=out_color_matrix=bt709 -c:v libx264 -pix_fmt yuv422p10le -profile:v high422 -g 1 -colorspace bt709 -color_trc bt709 -color_primaries bt709 -c:a pcm_s24le -f mov
mk xavc_s_h264_420_8bit.mp4 -c:v libx264 -pix_fmt yuv420p -c:a aac
mk hdr_hlg_bt2020.mov -vf "$PRE,zscale=t=linear,format=gbrpf32le,zscale=p=2020,zscale=t=arib-std-b67:m=2020_ncl:r=tv:npl=203,format=yuv420p10le" -c:v libx265 -x265-params log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc -tag:v hvc1 -c:a aac
mk hdr_pq_hdr10.mp4 -vf "$PRE,zscale=t=linear,format=gbrpf32le,zscale=p=2020,zscale=t=smpte2084:m=2020_ncl:r=tv:npl=203,format=yuv420p10le" -c:v libx265 -x265-params 'log-level=error:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc:hdr10=1:max-cll=1000,400' -c:a aac
mk hevc_444_12bit.mkv -c:v libx265 -pix_fmt yuv444p12le -x265-params log-level=error -c:a flac
mk prores_422hq_10bit.mov -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le -c:a pcm_s16le
mk prores_4444xq_alpha.mov -c:v prores_ks -profile:v 5 -pix_fmt yuva444p10le -c:a pcm_s24le
mk dnxhr_hqx_10bit.mxf -c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le -c:a pcm_s24le
mk dnxhr_444.mov -c:v dnxhd -profile:v dnxhr_444 -pix_fmt yuv444p10le -c:a pcm_s16le
mk xdcam_hd422_mpeg2_interlaced.mxf -c:v mpeg2video -pix_fmt yuv422p -flags +ilme+ildct -top 1 -b:v 50M -s 1920x1080 -c:a pcm_s24le
mk avchd_h264_interlaced.mts -c:v libx264 -pix_fmt yuv420p -flags +ilme+ildct -x264opts tff=1 -c:a ac3
mk h264_444_10bit.mkv -c:v libx264 -pix_fmt yuv444p10le -profile:v high444 -c:a aac
mk av1_10bit.mkv -c:v libsvtav1 -pix_fmt yuv420p10le -preset 12 -c:a libopus
mk vp9_10bit.webm -c:v libvpx-vp9 -pix_fmt yuv420p10le -deadline realtime -cpu-used 8 -c:a libopus
mk cineform_12bit.mov -c:v cfhd -pix_fmt gbrp12le -c:a pcm_s16le
mk uncompressed_v210_10bit.mov -c:v v210 -c:a pcm_s24le
mk ffv1_16bit_rgb48.mkv -c:v ffv1 -pix_fmt rgb48le -c:a flac
mk jpeg2000_12bit.mxf -c:v jpeg2000 -pix_fmt yuv444p12le -c:a pcm_s24le
mk mjpeg_422.avi -c:v mjpeg -pix_fmt yuvj422p -c:a pcm_s16le
mk dv_pal.dv -c:v dvvideo -s 720x576 -pix_fmt yuv420p -r 25 -c:a pcm_s16le -ac 2
for f in clip.braw clip.r3d; do head -c 200000 /dev/urandom > "$f"; done   # camera raw: needs a configured decoder
