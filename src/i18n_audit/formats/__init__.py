"""Parsers for each supported catalog format. Each returns a model.Catalog."""
from __future__ import annotations

from . import android, apple, jsonfile, pofile, properties, yamlfile

LOADERS = {
    "json": jsonfile.load,
    "yaml": yamlfile.load,
    "po": pofile.load,
    "android": android.load,
    "apple": apple.load,
    "properties": properties.load,
}


def load(fmt: str, path: str, rel: str, locale: str):
    return LOADERS[fmt](path, rel, locale)
