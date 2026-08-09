# Test Discovery Isolation Fix

Running both security modules in one Python process exposed an import-time
configuration cache issue. The application factory now accepts explicit config
overrides, and database initialization accepts the selected database path.

This prevents one test class from reusing another class's deleted temporary
database path and prevents clean initialization from targeting the root working
database.

Run:

```bat
python -m unittest discover tests -v
```
