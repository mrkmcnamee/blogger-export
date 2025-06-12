import argparse
import logging
import os
import shutil
from html.parser import HTMLParser
from typing import Dict, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests


TESTING = True  # Set to True for testing mode
POST_LIMIT = None
SCOPES = ["https://www.googleapis.com/auth/blogger"]

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.propagate = False

if TESTING:
    logger.setLevel(logging.DEBUG)
    logger.debug("Running in testing mode.")
    POST_LIMIT = 10


def get_credentials() -> Credentials:
    """
    Retrieves OAuth2 credentials for accessing the Blogger API.
    If the credentials are not found or are invalid, it prompts the user to
    log in.
    The file `token.json` stores the user's access and refresh tokens, and
    is created automatically when the authorization flow completes for the
    first time.

    Returns:
        Credentials: The OAuth2 credentials.
    """
    credentials = None

    if os.path.exists("token.json"):
        credentials = Credentials.from_authorized_user_file(
            "token.json", SCOPES
        )

    # If there are no (valid) credentials available, let the user log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret.json", SCOPES
            )
            credentials = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(credentials.to_json())

    return credentials


def get_blogger_posts(
        blog_id: str,
        credentials: Credentials,
        limit: int = None
        ) -> List:
    """
    Fetches all posts from a Blogger blog using the Blogger API.

    Args:
        blog_id (str): The ID of the Blogger blog.
        credentials (Credentials): The OAuth2 credentials to access the API.

    Returns:
        list: A list of posts from the blog.
    """
    service = build('blogger', 'v3', credentials=credentials)
    posts = []
    page_token = None

    while True:
        response = service.posts().list(
            blogId=blog_id, maxResults=50,
            pageToken=page_token,
        ).execute()
        posts.extend(response.get('items', []))
        page_token = response.get('nextPageToken')

        if not page_token:
            break

        if limit and len(posts) >= limit:
            posts = posts[:limit]
            break

    return posts


class ContentHTMLParser(HTMLParser):
    """
    Download images and replace URLs with local paths.
    """
    def __init__(self, output_dir: str, post_id: str):
        super().__init__()
        self.output_dir = output_dir
        self.post_id = post_id
        self.data = ""

    def handle_starttag(self, tag, attrs):
        self.data += f'<{tag}'
        for attr, value in attrs:
            if value.startswith("https://blogger.googleusercontent.com"):
                self.data += f' {attr}="{self._handle_user_content(value)}"'
            else:
                self.data += f' {attr}="{value}"'

        self.data += '>'

    def _handle_user_content(self, value: str) -> str:
        image_index = len(os.listdir(self.output_dir)) + 1 or 1
        filename = f"{self.post_id}-{image_index}.jpg"
        local_path = os.path.join(self.output_dir, filename)

        url = value if value.startswith("http") else "https:" + value
        download_image(url, local_path, credentials)

        return filename

    def handle_endtag(self, tag):
        if tag == 'img':
            pass
        else:
            self.data += f'</{tag}>'

    def handle_data(self, data):
        self.data += data


def download_image(url: str, local_path: str, credentials: Credentials) -> None:
    """
    Downloads an image from a URL and saves it to a local path.

    Args:
        url (str): The URL of the image to download.
        local_path (str): The local file path where the image will be saved.
        credentials (Credentials): The OAuth2 credentials for accessing the API.
    """
    headers = {
        "Authorization": f"Bearer {credentials.token}"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    with open(local_path, "wb") as file:
        file.write(response.content)


def convert_post_to_html(output_dir: str, post: Dict) -> str:
    """
    Converts a Blogger post to HTML format.

    Args:
        output_dir (str): The directory where the HTML file will be saved.
        post (dict): A dictionary representing a Blogger post.

    Returns:
        str: The HTML representation of the post.
    """
    id = post.get('id')
    title = post.get('title', 'No Title')
    published = post.get('published', 'Unknown Date')
    author = post.get('author', {}).get('displayName', 'Unknown Author')
    content = post.get('content', 'No Content')

    post_output_dir = os.path.join(output_dir, id)
    os.makedirs(post_output_dir, exist_ok=True)

    # Download images and replace URLs with local paths if necessary
    content_parser = ContentHTMLParser(post_output_dir, id)
    content_parser.feed(content)
    content = content_parser.data

    html_output = f"""
<article>
  <h1>{title}</h1>
  <div><strong>Published:</strong> {published}</div>
  <div><strong>Author:</strong> {author}</div>
  <div>{content}</div>
</article>
<p>
  <a href="../index.html">Back to index</a>
</p>
"""

    filename = os.path.join(post_output_dir, f"{id}.html")
    with open(filename, "w", encoding="utf-8") as file:
        file.write(html_output)

    logger.info(f"Converted post {id} to HTML: {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Blogger posts to HTML.")
    parser.add_argument("blog_id", help="The Blogger blog ID to export")
    args = parser.parse_args()

    BLOG_ID = args.blog_id

    credentials = get_credentials()

    posts = get_blogger_posts(BLOG_ID, credentials, limit=POST_LIMIT)
    logger.info(f"Retrieved {len(posts)} posts from blog ID {BLOG_ID}.")

    output_dir = os.path.join("output", BLOG_ID)
    shutil.rmtree(output_dir, ignore_errors=True)
    os.makedirs(output_dir, exist_ok=True)

    # Create index.html file
    index_html = """
<html>
  <head>
    <title>Blogger Posts</title>
  </head>
  <body>
    <h1>Blogger Posts</h1>
    <ul>
"""
    for i, post in enumerate(posts):
        index_html += f'<li><a href="{post["id"]}/{post["id"]}.html">{post["title"]}</a></li>'

    index_html += """
    </ul>
  </body>
</html>
"""
    logger.info(f"Created index.html with {len(posts)} posts.")

    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as index_file:
        index_file.write(index_html)

    for i, post in enumerate(posts):
        convert_post_to_html(output_dir, post)

    logger.info("Conversion completed successfully.")
