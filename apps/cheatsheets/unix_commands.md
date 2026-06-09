# Unix Commands Cheatsheet

## Navigation

| Command    | Use                         |
| ---------- | --------------------------- |
| `pwd`      | Show current directory      |
| `ls`       | List files                  |
| `ls -la`   | List all files with details |
| `cd <dir>` | Change directory            |
| `cd ..`    | Go up one directory         |
| `cd ~`     | Go to home directory        |
| `tree`     | Show folder tree            |

## Files and Folders

| Command                  | Use                   |
| ------------------------ | --------------------- |
| `touch file.txt`         | Create empty file     |
| `mkdir folder`           | Create folder         |
| `mkdir -p a/b/c`         | Create nested folders |
| `cp file.txt backup.txt` | Copy file             |
| `cp -r dir1 dir2`        | Copy folder           |
| `mv old.txt new.txt`     | Rename/move file      |
| `rm file.txt`            | Delete file           |
| `rm -r folder`           | Delete folder         |
| `rm -rf folder`          | Force delete folder   |
| `find . -name "*.py"`    | Find files by name    |

## Viewing Files

| Command               | Use               |
| --------------------- | ----------------- |
| `cat file.txt`        | Print file        |
| `less file.txt`       | Page through file |
| `head file.txt`       | First 10 lines    |
| `head -n 50 file.txt` | First 50 lines    |
| `tail file.txt`       | Last 10 lines     |
| `tail -f app.log`     | Follow live log   |
| `wc -l file.txt`      | Count lines       |

## Search Text

| Command                   | Use                     |              |
| ------------------------- | ----------------------- | ------------ |
| `grep "text" file.txt`    | Search in file          |              |
| `grep -r "text" .`        | Search recursively      |              |
| `grep -n "text" file.txt` | Show line numbers       |              |
| `grep -i "text" file.txt` | Case-insensitive search |              |
| `grep -v "text" file.txt` | Exclude matching lines  |              |
| `grep -E "a               | b" file.txt`            | Regex search |

## Printer Commands

| Command                       | Use                              |
| ----------------------------- | -------------------------------- |
| `lpstat -p`                   | Show printers and status         |
| `lpstat -v`                   | Show printer devices/URIs        |
| `lpstat -d`                   | Show default printer             |
| `lpstat -t`                   | Show full printer status         |
| `lpoptions -d PRINTER`        | Set default printer              |
| `lpq`                         | Show print queue                 |
| `lpq -P PRINTER`              | Show queue for specific printer  |
| `lpr file.pdf`                | Print file using default printer |
| `lpr -P PRINTER file.pdf`     | Print to specific printer        |
| `lp file.pdf`                 | Print file using CUPS            |
| `lp -d PRINTER file.pdf`      | Print to specific printer        |
| `lp -n 2 file.pdf`            | Print 2 copies                   |
| `lp -o landscape file.pdf`    | Print in landscape mode          |
| `cancel JOB_ID`               | Cancel print job                 |
| `cancel -a`                   | Cancel all jobs                  |
| `cancel -a PRINTER`           | Cancel all jobs on printer       |
| `cupsdisable PRINTER`         | Disable a printer                |
| `cupsenable PRINTER`          | Enable a printer                 |
| `cupsaccept PRINTER`          | Allow printer to accept jobs     |
| `cupsreject PRINTER`          | Stop printer from accepting jobs |
| `lpadmin -p PRINTER -E`       | Enable printer                   |
| `systemctl status cups`       | Check CUPS service               |
| `sudo systemctl restart cups` | Restart CUPS service             |

### Useful Printer Combos

| Command                     | Use                               |
| --------------------------- | --------------------------------- |
| `lpstat -p -d`              | Show printers and default printer |
| `lpstat -o`                 | Show active print jobs            |
| `lpstat -W completed`       | Show completed jobs               |
| `lpoptions -p PRINTER -l`   | Show printer options              |
| `echo "test" \| lp`         | Send test text to printer         |
| `lp -d PRINTER /etc/hosts`  | Quick test print                  |
| `lpstat -t \| grep PRINTER` | Check one printer in full status  |

## Pipes and Redirects

| Command              | Use                        |
| -------------------- | -------------------------- |
| `cmd > file.txt`     | Write output to file       |
| `cmd >> file.txt`    | Append output to file      |
| `cmd < file.txt`     | Use file as input          |
| `cmd1 \| cmd2`       | Pipe output                |
| `cmd 2> error.log`   | Redirect errors            |
| `cmd > out.log 2>&1` | Redirect output and errors |

## Permissions

| Command                      | Use                        |
| ---------------------------- | -------------------------- |
| `chmod +x script.sh`         | Make executable            |
| `chmod 644 file.txt`         | Owner write, everyone read |
| `chmod 755 script.sh`        | Executable script/folder   |
| `chown user file.txt`        | Change owner               |
| `chown -R user:group folder` | Change owner recursively   |

## Processes

| Command         | Use                      |
| --------------- | ------------------------ |
| `ps aux`        | List processes           |
| `top`           | Live process monitor     |
| `htop`          | Better live monitor      |
| `kill <pid>`    | Stop process             |
| `kill -9 <pid>` | Force stop process       |
| `pgrep python`  | Find process IDs         |
| `pkill python`  | Kill processes by name   |
| `jobs`          | Show background jobs     |
| `fg`            | Bring job to foreground  |
| `bg`            | Resume job in background |

## Disk and System

| Command               | Use                         |
| --------------------- | --------------------------- |
| `df -h`               | Disk free space             |
| `du -sh folder`       | Folder size                 |
| `du -h --max-depth=1` | Sizes of current subfolders |
| `free -h`             | Memory usage                |
| `uname -a`            | System info                 |
| `uptime`              | Uptime/load                 |
| `whoami`              | Current user                |
| `id`                  | User/group IDs              |

## Networking

| Command                    | Use                  |
| -------------------------- | -------------------- |
| `ping host.com`            | Test connectivity    |
| `curl url`                 | Fetch URL            |
| `curl -O url/file.zip`     | Download file        |
| `wget url`                 | Download file        |
| `ip addr`                  | Show IP addresses    |
| `ss -tulpen`               | Show listening ports |
| `ssh user@host`            | Connect by SSH       |
| `scp file user@host:/path` | Copy over SSH        |

## Archives

| Command                      | Use               |
| ---------------------------- | ----------------- |
| `tar -czf app.tar.gz folder` | Create `.tar.gz`  |
| `tar -xzf app.tar.gz`        | Extract `.tar.gz` |
| `zip -r app.zip folder`      | Create zip        |
| `unzip app.zip`              | Extract zip       |
| `gzip file.txt`              | Compress file     |
| `gunzip file.txt.gz`         | Decompress file   |

## Package Managers

### Debian / Ubuntu

| Command                | Use                  |
| ---------------------- | -------------------- |
| `sudo apt update`      | Refresh package list |
| `sudo apt upgrade`     | Upgrade packages     |
| `sudo apt install pkg` | Install package      |
| `sudo apt remove pkg`  | Remove package       |

### Fedora / RHEL

| Command                | Use             |
| ---------------------- | --------------- |
| `sudo dnf install pkg` | Install package |
| `sudo dnf remove pkg`  | Remove package  |
| `sudo dnf update`      | Update packages |

### macOS Homebrew

| Command              | Use              |
| -------------------- | ---------------- |
| `brew install pkg`   | Install package  |
| `brew uninstall pkg` | Remove package   |
| `brew update`        | Refresh Homebrew |
| `brew upgrade`       | Upgrade packages |

## Useful Combos

| Command                                | Use                        |
| -------------------------------------- | -------------------------- |
| `ls -lt`                               | Sort files by newest first |
| `ls -lhS`                              | Sort files by size         |
| `find . -type f -size +100M`           | Find files over 100 MB     |
| `find . -type f -mtime -1`             | Files changed in last day  |
| `find . -type f -name "*.log" -delete` | Delete log files           |
| `grep -rn "TODO" .`                    | Find TODOs recursively     |
| `tail -f app.log \| grep ERROR`        | Watch errors live          |
| `ps aux \| grep python`                | Find Python processes      |
| `du -sh * \| sort -h`                  | Sort folders by size       |
| `history \| grep ssh`                  | Search command history     |

## Safety Notes

| Command          | Warning                              |
| ---------------- | ------------------------------------ |
| `rm -rf /`       | Catastrophic delete                  |
| `rm -rf *`       | Deletes everything in current folder |
| `chmod -R 777 .` | Usually a bad idea                   |
| `sudo`           | Runs with admin privileges           |
| `kill -9`        | Force kills without cleanup          |
