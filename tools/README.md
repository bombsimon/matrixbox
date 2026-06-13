# Tools

Tools used for development and iteration of the software and applications.

## Pushing files to device

The device doesn't have any SSH or FTP server, however the HTTP server that
serves the file manager supports uploading files. This can be used to quickly
push code to the device remotely without having to plug it into the computer.

Since the server treats binary files differently from text, you can either rely
on auto-discovery or force binary mode, which uses the REPL to encode and decode
the binary bytes. This is used for `.mpy` files.

```sh
# Usage: python3 tools/push.py <local> <device_path> [--host IP]
#
# Example:
MATRIXBOX_HOST=192.168.1.10 python3 tools/push.py apps/my_app/code.mpy /my_app/code.mpy
```
