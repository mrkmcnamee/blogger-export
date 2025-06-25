# Blogger export

## Getting started

1. Follow the instructions in [Blogger API](https://developers.google.com/blogger) for getting OAuth credentials.
   Place them in `client_secret.json`. It should look like this:

   ```json
     {
       "installed": {
         "client_id": "xxxxxxxxxxx.apps.googleusercontent.com",
         "project_id": "my-project-id-123456",
         "auth_uri": "https://accounts.google.com/o/oauth2/auth",
         "token_uri": "https://oauth2.googleapis.com/token",
         "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
         "client_secret": "xxxxxxxxxxxxxx",
         "redirect_uris": [
           "http://localhost"
         ]
       }
     }
   ```

2. Log in to [Blogger](https://www.blogger.com) and select the blog to export. Note the Blog ID in the browser's URL.

3. Install [Python](https://www.python.org/downloads/).

4. Install [GitHub Desktop](https://desktop.github.com/download/) and checkout this repository.

## Performing a test run

1. First run in test mode (i.e. export the latest 10 posts) to verify that the export is working. This will write the
   results to `blogs_test\<Blog ID>\`.

    ```shell
    python .\blogger-export.py <Blog ID>
    ```

2. Open the HTML index file in the browser to see the results: `blogs_test\<Blog ID>\index.html` to view the results.

3. Re-run as often as necessary, the previously generated files will be overwritten.

## Preforming a full run

1. Export the full blog. This will write the results to `blogs\<Blog ID>\index.html`. This will not overwrite previously
   generated files, but will skip existing exported posts. This allows the export to continue if it has been interrupted.
   A semaphore is used to detect incompletely exported posts and to restart their export.

    ```shell
    python .\blogger-export.py <Blog ID> --full
    ```

2. Open the index file again in the browser to see the results.

3. To re-run the full export:

    ```shell
    python .\blogger-export.py <Blog ID> --full --clean
    ```

## Multiple blogs

Repeat the process for each Blogger blog. They are each stored in a separate directory so will not overwrite each other when running.
