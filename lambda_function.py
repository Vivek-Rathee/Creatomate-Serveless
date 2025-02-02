import os
import time
import json
import requests
import boto3

# Initialize the S3 client
s3_client = boto3.client('s3')

def generate_creative_text(openai_api_key, prompt, model="gpt-3.5-turbo"):
    """
    Uses the OpenAI ChatGPT API to generate creative text.
    """
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Write me a 5 word inspiring quote"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        creative_text = data["choices"][0]["message"]["content"].strip()
        return creative_text
    else:
        raise Exception(f"Error calling OpenAI API: {response.status_code} {response.text}")

def create_creatomate_render(creatomate_api_key, creative_text):
    """
    Creates a render on Creatomate using the provided creative text.
    """
    url = 'https://api.creatomate.com/v1/renders'
    headers = {
        "Authorization": f"Bearer {creatomate_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "template_id": "XXXX63c7-f596-492e-b158-02ce730b3992",  # Your template ID
        "modifications": {
            "Video.source": "https://creatomate.com/files/assets/7347c3b7-e1a8-4439-96f1-f3dfc95c3d28",
            "Text-1.text": creative_text,
            "Text-2.text": "Create & Automate\n[size 150%]Video[/size]"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code in [200, 201, 202]:
        data = response.json()
        # If the response is a list, extract the first render object.
        render_object = data[0] if isinstance(data, list) and data else data
        render_id = render_object.get("id")
        if not render_id:
            raise Exception("Render ID not found in Creatomate response")
        return render_id
    else:
        raise Exception(f"Error calling Creatomate API: {response.status_code} {response.text}")

def poll_render_status(render_id, creatomate_api_key, interval=5, max_attempts=20):
    """
    Polls the render status every `interval` seconds until the render is complete,
    or until max_attempts is reached.
    """
    url = f"https://api.creatomate.com/v1/renders/{render_id}"
    headers = {
        "Authorization": f"Bearer {creatomate_api_key}",
        "Content-Type": "application/json"
    }
    attempts = 0
    while attempts < max_attempts:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Error retrieving render status: {response.status_code} {response.text}")
        data = response.json()
        status = data.get("status")
        print(f"Attempt {attempts + 1}: Current render status: {status}")
        # Treat both 'finished' and 'succeeded' as final states
        if status in ("finished", "succeeded"):
            return data.get("url")
        elif status in ("failed", "cancelled"):
            raise Exception("Render failed or was cancelled")
        time.sleep(interval)
        attempts += 1
    raise Exception("Max attempts reached while polling render status")

def download_video(video_url, file_path="/tmp/final_video.mp4"):
    """
    Downloads the video from the given URL and saves it to file_path.
    """
    print(f"Downloading video from: {video_url}")
    response = requests.get(video_url, stream=True)
    if response.status_code == 200:
        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        return file_path
    else:
        raise Exception(f"Error downloading video: {response.status_code}")

def upload_to_s3(file_path, bucket, key):
    """
    Uploads the file at file_path to the specified S3 bucket with the given key.
    """
    if not os.path.exists(file_path):
        print(f"File {file_path} does not exist.")
        return

    file_size = os.path.getsize(file_path)
    print(f"File {file_path} exists and is {file_size} bytes. Proceeding with upload...")

    try:
        s3_client.upload_file(file_path, bucket, key)
        print(f"Uploaded {file_path} to s3://{bucket}/{key}")
    except Exception as e:
        print(f"Error uploading file to S3: {e}")
        raise

def lambda_handler(event, context):
    # Retrieve API keys from environment variables (set these in your Lambda configuration)
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    creatomate_api_key = os.environ.get("CREATOMATE_API_KEY")
    s3_bucket = "YOUR_BUCKET_NAME"  # Your S3 bucket name

    if not openai_api_key or not creatomate_api_key:
        return {
            'statusCode': 500,
            'body': json.dumps("API keys not provided")
        }
    
    # Step 1: Generate creative text using the OpenAI API
    prompt = "Generate a creative social media post caption for a promotional video."
    try:
        creative_text = generate_creative_text(openai_api_key, prompt)
        print("Creative text generated:", creative_text)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error generating creative text: {str(e)}")
        }
    
    # Step 2: Create a render on Creatomate using the creative text
    try:
        render_id = create_creatomate_render(creatomate_api_key, creative_text)
        print("Creatomate render initiated. Render ID:", render_id)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error creating render: {str(e)}")
        }
    
    # Step 3: Poll for render completion
    try:
        final_video_url = poll_render_status(render_id, creatomate_api_key, interval=5, max_attempts=20)
        print("Final video URL:", final_video_url)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error polling render status: {str(e)}")
        }
    
    # Step 4: Download the video and upload it to S3
    try:
        local_file_path = download_video(final_video_url, file_path="/tmp/final_video.mp4")
        s3_key = "final_video.mp4"
        upload_to_s3(local_file_path, s3_bucket, s3_key)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error downloading/uploading video: {str(e)}")
        }
    
    return {
        'statusCode': 200,
        'body': json.dumps(f"Video successfully processed and uploaded to s3://{s3_bucket}/{s3_key}")
    }
