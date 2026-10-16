#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

ffmpeg -y -ss 1.0 -to 3.0 -i b0 -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -an -t 2.0 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_00.mp4
ffmpeg -y -ss 0.125 -to 3.875 -i b1 -ss 0.125 -to 3.875 -i sb -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -map 1:a:0? -t 3.75 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_01.mp4
ffmpeg -y -ss 0.125 -to 3.875 -i b2 -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -an -t 3.75 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_02.mp4
ffmpeg -y -ss 0.125 -to 3.875 -i b3 -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -an -t 3.75 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_03.mp4
ffmpeg -y -ss 0.125 -to 3.875 -i b4 -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -an -t 3.75 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_04.mp4
ffmpeg -y -ss 0.125 -to 3.875 -i b5 -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -an -t 3.75 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_05.mp4
ffmpeg -y -ss 0.125 -to 3.875 -i b6 -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -an -t 3.75 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_06.mp4
ffmpeg -y -ss 0 -to 4.0 -i hero -vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p -map 0:v:0 -map 0:a:0? -t 4.0 -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -ar 44100 unused/seg_07.mp4
ffmpeg -y -f concat -safe 0 -i unused/concat.txt -c copy unused/output.mp4
