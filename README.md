# oa2zenodo.py

This script helps automate the creation of records on Zenodo, for a conference managed on Oxford Abstracts.

It was developed for RSECon24, so may require modification for other conferences if their Oxford Abstracts custom form responses differ.

Files to be attached to records are automatically detected within the hierarchy of a programme upload folder, based on parent directory that can be ignored. If the directory contains a folder named `zenodo`, only files from that directory will be used.

## Usage

```sh
python3 oa2zenodo.py <conf file>
```
*If `conf file` is not provided `rsecon24.ini` will be attempted.*

## Limitations

* It's still a manual process to export slides from javascript (e.g. via appending `?print-pdf` to the url) or Google Slides.
* Zenodo API is very picky about funding, so this is currently a manual task.
