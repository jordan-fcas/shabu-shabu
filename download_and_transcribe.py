import time
import random
import instaloader
import whisper
import os
import yt_dlp
import shutil
from moviepy.editor import VideoFileClip
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import re

class Downloader:
    """Base class for handling retries and rate limits."""
    def __init__(self, max_retries=5, backoff_factor=2):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
    
    def preemptive_backoff(self, num_urls):
        """Preemptive backoff proportional to the number of videos."""
        wait_time = num_urls * random.uniform(1, 3) # Adjust range as needed
        print(f"Preemptively backing off for {wait_time:.2f} seconds based on {num_urls} URLs...")
        time.sleep(wait_time)

    def retry(self, function, *args, **kwargs):
        """Retry mechanism with exponential backoff."""
        retries = 0
        while retries < self.max_retries:
            try:
                return function(*args, **kwargs)
            except instaloader.exceptions.TooManyRequestsException:
                wait_time = self.backoff_factor ** retries + random.uniform(0, 1)
                print(f"Rate limit hit. Retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
                retries += 1
        print("Max retries reached. Could not complete the request.")
        return None
        

class Transcriber(Downloader):
    def __init__(self, urls, model_name="base.en", max_retries=5, backoff_factor=2):
        super().__init__(max_retries, backoff_factor)
        # Intialize Whisper model
        self.model = whisper.load_model(model_name)
        self.urls = urls
        self.loader = instaloader.Instaloader()
        self.all_transcriptions = {}

    def download_instagram_videos(self, url, loader):
        """Download all videos from an Instagram post."""
        # loader = instaloader.Instaloader()
        try:
            shortcode = url.split("/")[-2]

            self.retry(loader.download_post, instaloader.Post.from_shortcode(loader.context, shortcode), target=shortcode)

            # loader.download_post(instaloader.Post.from_shortcode(loader.context, shortcode), target=shortcode)

            video_paths = []

            for file_name in os.listdir(shortcode):
                if file_name.endswith('.mp4'):
                    video_path = os.path.join(shortcode, file_name)
                    video_paths.append(video_path)
                
            if video_paths:
                print(f"Videos downloaded successfulyy: {video_paths}")
                return video_paths, shortcode
            else:
                print("No videos found in the post.")
                return None, shortcode
        except Exception as e:
            print(f"An error occurred: {e}")
            return None, None
    
    def download_tiktok_video(self, url, output_path='.'):
        """Download a TikTok video."""
        ydl_opts = {
            'outtmpl': f'{output_path}/%(title)s.%(ext)s',
            'no_check_certificate': True,  # Bypass certificate verification
            'no-playlist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_title = info_dict.get('title', 'video')
            video_ext = info_dict.get('ext', 'mp4')
            video_path = os.path.join(output_path, f"{video_title}.{video_ext}")

            if os.path.exists(video_path):
                print(f'Download complete: {video_path}')
                return video_path
            else:
                print("Error: File not found.")
                return None
    
    def safe_delete_directory(self, directory):
        """Safely delete a directory if it's not empty or set to a dangerous path."""
        if directory and os.path.isdir(directory):
            if directory in ['.', '/']:
                print(f"Skipping dangerous delete operation: {directory}")
            else:
                shutil.rmtree(directory)
                print(f"Deleted download directory: {directory}")
        else:
            print(f"Directory not found or unsafe to delete: {directory}")
    
    def transcribe_videos(self, videos, download_dir):
        """Transcribe the audio from a list of video files using Whisper."""
        transcriptions = {}

        for idx, video_path in enumerate(videos):
            video = VideoFileClip(video_path)

            audio_path = f"{os.path.splitext(video_path)[0]}_{idx}.mp3"

            video.audio.write_audiofile(audio_path)
            print(f"Extracted audio: {audio_path}")

            result = self.model.transcribe(audio_path)

            transcription = ''.join([segment['text'] for segment in result['segments']])

            if transcription.strip():
                video_key = f"video_{idx}"
                transcriptions[video_key] = transcription
                print(f"Transcriptions for {video_key}: {transcription}")
            else:
                print(f"No speech detected in video {idx}, skipping transcription.")

            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"Deleted audio file: {audio_path}")
            
            if os.path.exists(video_path):
                os.remove(video_path)
                print(f"Deleted video file: {video_path}")
        
        if download_dir:
            self.safe_delete_directory(download_dir)
        
        return transcriptions

    def get_video_id(self, url):
        # Extract the video ID from the URL using a regular expression
        video_id = re.search(r'(?<=v=)[\w-]+|(?<=be/)[\w-]+', url)
        print(video_id.group(0))
        return video_id.group(0) if video_id else None
        # Regular expression to capture YouTube video ID from different types of URLs
        # pattern = (
        #     r"(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/|embed/|v/)|youtu\.be/)"
        #     r"(?P<id>[a-zA-Z0-9_-]{11})"
        # )
        
        # match = re.search(pattern, url)
        
        # if match:
        #     return match.group("id")
        # else:
        #     return None
    
    def process_urls(self):
        """Process all URLs initialized with the class and transcribe videos."""

        num_urls = len(self.urls)

        for url in self.urls:
            self.preemptive_backoff(num_urls)
            print(f"Processing URL: {url}")
            if "instagram.com" in url:
                videos, download_dir = self.download_instagram_videos(url, self.loader)
            elif "tiktok.com" in url:
                videos = [self.download_tiktok_video(url)]
                if videos[0]:
                    download_dir = os.path.dirname(videos[0])
                else:
                    download_dir = None
            elif "youtube.com" in url:
                # Get the video ID
                video_id = self.get_video_id(url)
                
                if not video_id:
                    print("Invalid YouTube URL")

                # Fetch the transcript
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, ['en'])
                    formatter = TextFormatter()
                    transcript = formatter.format_transcript(transcript_list)
                    self.all_transcriptions[url] = transcriptions
                    continue
                except:
                    videos = [self.download_tiktok_video(url)]
                    if videos[0]:
                        download_dir = os.path.dirname(videos[0])
                    else:
                        download_dir = None
            else:
                print(f"Unsupported URL: {url}")
                continue
        
            if videos:
                transcriptions = self.transcribe_videos(videos, download_dir)
                self.all_transcriptions[url] = transcriptions
            else:
                print(f"No videos found for URL: {url}")
        
        return self.all_transcriptions


transcriber = Transcriber(urls=["https://www.tiktok.com/@tonggeqichezhishi/video/7405039394328939806?is_from_webapp=1&sender_device=pc", "https://www.instagram.com/p/C_gNPhCRidF/", "https://www.instagram.com/p/C_51Jyhx59k/", "https://www.instagram.com/p/C_1JODaPW1y/"])

transcriber.process_urls()

print(transcriber.all_transcriptions)
