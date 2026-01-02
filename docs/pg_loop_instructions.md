# PostgreSQL Loop-Back Image Access Guide

The Spotify monitor now stores its PostgreSQL cluster inside a 1 GiB ext4 disk image located at:

```
/media/$USER/Samsung USB/postgresql/pgdata.img
```

This file lives on the Samsung drive (vfat) and is mounted on Linux at `/mnt/spotify_pgdata` via `/etc/fstab`. The Postgres server expects this mount to be present before startup.

## How it works on Linux
- `/etc/fstab` contains:
  ```
  /media/$USER/Samsung USB/postgresql/pgdata.img /mnt/spotify_pgdata ext4 loop,defaults 0 2
  ```
- Systemd mounts the loop-backed filesystem during boot. If the Samsung drive is missing, PostgreSQL will fail to start.
- Manual remount:
  ```bash
  sudo umount /mnt/spotify_pgdata
  sudo mount -o loop "/media/$USER/Samsung USB/postgresql/pgdata.img" /mnt/spotify_pgdata
  ```

## Accessing the data from Windows via WSL
1. Plug the Samsung drive into Windows. It should appear as a normal removable drive (e.g., `E:`). Inside, you will see `postgresql/pgdata.img`.
2. Open WSL (Ubuntu/Debian). Ensure `e2fsprogs` is installed (`sudo apt install e2fsprogs`).
3. Create a mount point inside WSL:
   ```bash
   sudo mkdir -p /mnt/wsl_pgloop
   ```
4. Mount the image read-only (recommended while the Raspberry Pi is not using it):
   ```bash
   sudo mount -o loop,ro "/mnt/e/Samsung USB/postgresql/pgdata.img" /mnt/wsl_pgloop
   ```
   - Replace `/mnt/e/` with the actual WSL path for your Windows drive (WSL maps `E:` to `/mnt/e`).
   - Keep the mount read-only unless the Raspberry Pi PostgreSQL service is stopped and the Linux mount is unmounted.
5. Inspect files as needed, then detach:
   ```bash
   sudo umount /mnt/wsl_pgloop
   ```

### Editing the database from WSL
If you must write to the cluster from WSL:
1. Stop PostgreSQL on the Raspberry Pi (`sudo systemctl stop postgresql`).
2. Unmount `/mnt/spotify_pgdata` on the Pi.
3. Mount the image read-write in WSL (`sudo mount -o loop,rw ...`).
4. After finishing, unmount in WSL and remount/start PostgreSQL on the Pi.

## Backup tips
- Copy `pgdata.img` to another drive while PostgreSQL is stopped to take a full backup.
- Alternatively, use `pg_dump` regularly and store dumps on the Samsung drive outside the image for easier Windows access.
