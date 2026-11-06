**Title**: Add a `--json` output flag to the CLI

**Description**: Add a `--json` flag to `textkit` (`textkit/cli.py`). When given, print a single JSON object `{"op": <operation name>, "result": <result>}` instead of the plain result. Without the flag, output is unchanged.
