import { Config } from "@remotion/cli/config";

// H.264 vertical reel. faststart so Instagram can begin playback before the whole
// file downloads (same reason the PIL pipeline passed +faststart to ffmpeg).
Config.setVideoImageFormat("jpeg");
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setConcurrency(null); // let Remotion pick based on cores
