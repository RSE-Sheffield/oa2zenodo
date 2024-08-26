# oa2zenodo.py

This script helps automate the creation of records on Zenodo, for a conference managed on Oxford Abstracts.

It was developed for RSECon24, so may require modification for other conferences if their Oxford Abstracts custom form responses differ.

Files to be attached to records are handles via user input, based on parent directory selected.

## Usage

```sh
python3 oa2zenodo.py <conf file>
```
*If `conf file` is not provided `rsecon24.ini` will be attempted.*