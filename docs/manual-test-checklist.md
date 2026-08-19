# Manual Test Checklist

No hardware test should be run by default.

Real destructive tests require explicit tester consent and disposable USB drives. Installing Ventoy erases the selected USB drive.

## Hardware Cases

- One USB drive happy path: confirm a single disposable USB drive is listed, selected, confirmed, prepared with Ventoy, and receives the expected ISO files.
- Two USB drives in parallel: confirm two disposable USB drives can run concurrently without cross-device status or log confusion.
- Device removed before install: select a disposable USB drive, remove it before the destructive install step, and confirm the job refuses to continue.
- Device removed during copy: remove a disposable USB drive during ISO copy and confirm the affected job fails clearly without affecting unrelated jobs.
- Existing mounted partitions: start with mounted partitions on a disposable USB drive and confirm the workflow unmounts only that drive's partitions before installation.
- Missing Windows ISO with manual fallback: omit a Windows ISO and confirm the UI shows manual instructions to download it from Microsoft and place it in `./isos`.
