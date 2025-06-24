# Blogger export

## Getting started

1. Follow the instructions in [Blogger API](https://developers.google.com/blogger) for getting OAuth credentials.
   Place them in `client_secret.json`.

2. Log in to [Blogger](https://www.blogger.com) and select the blog to export. Note the Blog ID in the browser's URL.

3. Install [Python](https://www.python.org/downloads/).

4. Install [GitHub Desktop](https://desktop.github.com/download/) and checkout this repository.

## Performing a test run

1. First run in test mode (i.e. export the latest 10 posts) to verify that the export is working. Rerun if necessary,
   the previously generated files will be overwritten.

    ```shell
    python .\blogger-export.py <Blog ID>
    ```

2. Open the HTML index file in the browser to see the results: `blogs\<Blog ID>\index.html` to view the results.

## Preforming a full run

1. Export the full blog, this will overwrite the previously generated files.

    ```shell
    python .\blogger-export.py <Blog ID> --full
    ```

2. Open the index file again in the browser to see the results.

## Multiple blogs

Repeat the process for each Blogger blog. They are each stored in a separate directory so will not overwrite each other when running.
