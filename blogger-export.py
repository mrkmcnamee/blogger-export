import argparse
from datetime import datetime, timezone
import logging
import os
import shutil
from html.parser import HTMLParser
import sys
from typing import Dict, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import requests


POST_EXPORT_TEST_LIMIT = 10
SCOPES = ["https://www.googleapis.com/auth/blogger"]

logger = logging.getLogger(__name__)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)
logger.propagate = False
logger.setLevel(logging.INFO)


def get_credentials() -> Credentials:
    """
    Retrieves OAuth2 credentials for accessing the Blogger API.
    If the credentials are not found or are invalid, it prompts the user to log in.
    The file `token.json` stores the user's access and refresh tokens, and
    is created automatically when the authorization flow completes for the first time.

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


def get_blogger_blog(blog_id: str, credentials: Credentials) -> Dict:
    """
    Fetches a Blogger blog by its ID using the Blogger API.

    Args:
        blog_id (str): The ID of the Blogger blog.
        credentials (Credentials): The OAuth2 credentials to access the API.

    Returns:
        dict: A dictionary representing the Blogger blog.
    """
    service = build('blogger', 'v3', credentials=credentials)
    blog = service.blogs().get(blogId=blog_id).execute()

    return blog


def get_blogger_posts(
        blog_id: str,
        credentials: Credentials,
        limit: int = None,
        specific_post: str = None
        ) -> List:
    """
    Fetches all posts or a specific post from a Blogger blog using the Blogger API.

    Args:
        blog_id (str): The ID of the Blogger blog.
        credentials (Credentials): The OAuth2 credentials to access the API.
        limit (int, optional): The maximum number of posts to fetch. Defaults to None.
        specific_post (str, optional): The ID of a specific post to fetch. Defaults to None.

    Returns:
        list: A list of posts from the blog.
    """
    service = build('blogger', 'v3', credentials=credentials)
    posts = []
    page_token = None

    if specific_post:
        logger.info(f"Fetching specific post: {specific_post}")
        post = service.posts().get(blogId=blog_id, postId=specific_post).execute()
        return [post]

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
    Download the HTML and images and replace URLs with local paths.
    """
    def __init__(self, output_dir: str, post_id: str):
        super().__init__()
        self.output_dir = output_dir
        self.post_id = post_id
        self.image_index = 0
        self.data = ""

    def handle_starttag(self, tag, attrs):
        self.data += f'<{tag}'
        for attr, value in attrs:
            if value and value.startswith("https://blogger.googleusercontent.com"):
                if attr == 'href':
                    self.image_index += 1
                    self.data += f' {attr}="{self._handle_user_content(value, "full", self.image_index)}"'
                elif attr == 'src':
                    self.data += f' {attr}="{self._handle_user_content(value, "thumbnail", self.image_index)}"'
            else:
                self.data += f' {attr}="{value}"'

        self.data += '>'

    def _handle_user_content(self, value: str, image_type: str, image_index: int) -> str:
        """
        Handles the user content by downloading the image and returning the local filename.
        Args:
            value (str): The URL of the image.
            image_type (str): The type of image (e.g., "thumbnail", "full").
            image_index (int): The index of the image in the post.
        Returns:
            str: The local filename where the image is saved.
        """
        filename = f"{self.post_id}_{image_type}_{image_index}.jpg"
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


class ImgSrcExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.source_urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            for attr, value in attrs:
                if attr == "src":
                    self.source_urls.append(value)


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

    if 'text/html' in response.headers.get('Content-Type', ''):
        logger.info("  Expected an image but received HTML content.")
        parser = ImgSrcExtractor()
        parser.feed(response.content.decode('utf-8'))

        if len(parser.source_urls) > 0:
            download_image(parser.source_urls[0], local_path, credentials)
            logger.info("  Extracted image from HTML content.")
        else:
            logger.warning("  No image found in HTML content, skipping.")
    else:
        with open(local_path, "wb") as file:
            file.write(response.content)


def convert_post_to_html(output_dir: str, navigation: Dict, post: Dict, specific_post: str = None) -> str:
    """
    Converts a Blogger post to HTML format.

    Args:
        output_dir (str): The directory where the HTML file will be saved.
        post (dict): A dictionary representing a Blogger post.
        specific_post (str, optional): The ID of a specific post to convert. Defaults to None.

    Returns:
        str: The path to the generated HTML file.
    """
    id = post.get('id')
    title = post.get('title', 'No Title')
    published = to_utc_str(post.get('published', 'Unknown Date'))
    author = post.get('author', {}).get('displayName', 'Unknown Author')
    url = post.get('url', '#')
    content = post.get('content', 'No Content')

    post_output_dir = os.path.join(output_dir, id)
    html_filename = os.path.join(post_output_dir, f"{id}.html")
    blog_filename = os.path.join(output_dir, "blog_source.html")
    semaphore = os.path.join(post_output_dir, "semaphore.txt")

    if os.path.exists(semaphore):
        logger.warning(f"Incomplete conversion of post {id} detected, cleaning up.")
        shutil.rmtree(post_output_dir, ignore_errors=True)

    try:
        os.makedirs(post_output_dir)
    except FileExistsError:
        logger.warning(f"Skipped post {id}: Directory already exists")
        return html_filename

    with open(semaphore, "w", encoding="utf-8") as file:
        file.write("")

    if specific_post:
        logger.info("Saving source HTML for specific post.")
        with open(blog_filename, "w", encoding="utf-8") as file:
            file.write(content)

    # Download images and replace URLs with local paths
    content_parser = ContentHTMLParser(post_output_dir, id)
    content_parser.feed(content)
    content = content_parser.data

    html_output = f"""
<html>
  <head>
    <title>{title}</title>
  </head>
  <body>
    </article>
      <h1>{title}</h1>
      <div><strong>Published:</strong> {published}</div>
      <div><strong>Author:</strong> {author}</div>
      <div>{content}</div>
    </article>
    <p>
      <a href="{navigation[id]['previous']}">Previous Post</a> |
      <a href="{navigation[id]['next']}">Next Post</a>
    </p>
    <p>
      <a href="../index.html">Back to index</a>
    </p>
    <p>
      <a href="{url}" target="_blank">View on Blogger</a>
    </p>
  </body>
</html>
"""

    with open(html_filename, "w", encoding="utf-8") as file:
        file.write(html_output)

    logger.info(f"Converted post {id} to HTML: {html_filename}")

    os.remove(semaphore)

    return html_filename


def to_utc_str(dt_str: str) -> str:
    """
    Converts a datetime string to UTC format.
    Args:
        dt_str (str): The datetime string in ISO format.
    Returns:
        str: The datetime string in UTC format.
    """
    try:
        dt = datetime.fromisoformat(dt_str)
        dt_utc = dt.astimezone(timezone.utc)

        return dt_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return None


def create_navigation_links(posts: List) -> Dict:
    """
    Creates backwards and forwards navigation links for the posts.

    Args:
        posts (list): A list of Blogger posts.
    Returns:
        dict: A dictionary containing the navigation links for each post.
    """
    fallback_url = "../index.html"
    post_count = len(posts)

    navigation = {}
    for i, post in enumerate(posts):
        if i > 0:
            previous_post_id = posts[i - 1]["id"]
            previous_url = f"../{previous_post_id}/{previous_post_id}.html"
        else:
            previous_url = fallback_url

        if i < post_count-1:
            next_post_id = posts[i + 1]["id"]
            next_url = f"../{next_post_id}/{next_post_id}.html"
        else:
            next_url = fallback_url

        navigation[post["id"]] = {
            "previous": previous_url,
            "next": next_url
        }

    return navigation


def create_index_html(output_dir: str, blog: Dict, posts: List) -> str:
    """
    Creates an index HTML file listing all posts.

    Args:
        output_dir (str): The directory where the index file will be saved.
        blog (dict): A dictionary representing the Blogger blog.
        posts (list): A list of Blogger posts.
    Returns:
        str: The path to the generated index HTML file.
    """

    blog_name = blog.get("name", "Blogger Blog")
    blog_url = blog.get("url", "#")
    blog_post_count = blog["posts"]["totalItems"]
    blog_export_count = len(posts)
    exported_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    index_html = f"""
<html>
  <head>
    <title>{blog_name}</title>
  </head>
  <body>
    <h1>{blog_name}</h1>
    <p><b>Total Posts:</b> {blog_post_count}</p>
    <p><b>Exported on:</b> {exported_on}</p>
    <p><a href="{blog_url}" target="_blank">View on Blogger</a></p>
    <ul>
"""

    for i, post in enumerate(posts):
        post_id = post.get("id")
        post_title = post.get("title", "No Title")
        post_published = to_utc_str(post.get("published", "Unknown Date"))

        index_html += f'      <li>{post_published} &ndash; <a href="{post_id}/{post_id}.html">{post_title}</a></li>\n'

    index_html += f"""
    </ul>
    <p><b>Exported Posts:</b> {blog_export_count}</p>
  </body>
</html>
"""
    logger.info("Created index.html.")

    filename = os.path.join(output_dir, "index.html")
    with open(filename, "w", encoding="utf-8") as index_file:
        index_file.write(index_html)

    return filename


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Blogger posts to HTML.")
    parser.add_argument("blog_id", help="The Blogger blog ID to export")
    parser.add_argument("--post", help="Export a specific post by ID", default=None)
    parser.add_argument("--full", action="store_true",  help="Export all posts in the blog")
    parser.add_argument("--clean", action="store_true", help="Clean the output directory before export")
    args = parser.parse_args()

    BLOG_ID = args.blog_id
    FULL_EXPORT = args.full
    CLEAN_OUTPUT = args.clean
    SPECIFIC_POST = args.post

    if FULL_EXPORT and SPECIFIC_POST:
        logger.error("Cannot specify both --full and --post options.")
        sys.exit(1)

    if FULL_EXPORT:
        base_output_dir = "blogs"
    elif SPECIFIC_POST:
        base_output_dir = f"blogs_{SPECIFIC_POST}"
    else:
        base_output_dir = "blogs_test"

    credentials = get_credentials()

    if not FULL_EXPORT:
        logger.debug("Running in testing mode")
        logger.setLevel(logging.DEBUG)

    output_dir = os.path.join(base_output_dir, BLOG_ID)
    logger.info(f"Output directory: {output_dir}")

    if not FULL_EXPORT or CLEAN_OUTPUT:
        logger.info("Deleting output directory before export.")
        shutil.rmtree(output_dir, ignore_errors=True)

    os.makedirs(output_dir, exist_ok=True)

    log_filename = f"blogger_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = os.path.join(output_dir, log_filename)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    blog = get_blogger_blog(BLOG_ID, credentials)
    logger.info(f"Processing blog: {blog['name']} (ID: {blog['id']})")

    limit = POST_EXPORT_TEST_LIMIT if not FULL_EXPORT else None
    posts = get_blogger_posts(BLOG_ID, credentials, limit, SPECIFIC_POST)
    logger.info(f"Retrieved {len(posts)} posts.")

    index_html = create_index_html(output_dir, blog, posts)
    navigation = create_navigation_links(posts)

    for i, post in enumerate(posts):
        convert_post_to_html(output_dir, navigation, post, SPECIFIC_POST)

    logger.info("Conversion completed successfully.")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Open the {index_html} file to view the exported posts.")
