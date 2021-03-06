#!/usr/bin/env python3
'''
A command line program to mount an encrypted encfs filesystem while another
program executes.
'''
import argparse
import getpass
import hashlib
import os
import subprocess
import tempfile
try:    #removes T(t)kinter issue between 2.x and 3.x
    import Tkinter as tk
except ImportError:
    import tkinter as tk
import time


class TkinterMsg(tk.Tk):
    '''
    shows a simple messagebox
    :Args:
        * title (str) - tk title text
        * message (str) - message text
    '''
    def __init__(self, title=None, message=None):
        super().__init__()
        self.title(title)
        # Declare widgets
        self.frame = tk.Frame(self)
        self.msg = tk.Label(self.frame,
                                 text=message,
                                 fg='red')
        self.button = tk.Button(self.frame,
                                     text='OK',
                                     command=self.destroy)
        # Pack everything up
        self.frame.pack()
        self.msg.pack()
        self.button.pack()
        self.bind('<Return>', lambda key: self.destroy())

        self.mainloop()


class Tkinter_Input(tk.Tk):
    '''
    class to get password from the user using tk
    :Args:
        * message (str) - error message text displayed in red
    :Attr:
        * password (str) - the password entered by the user.
        * canceled (bool) - did the user push the cancel button
    '''

    def __init__(self, message=None):
        tk.Tk.__init__(self)
        self.title('Encfswrapper')
        self.password = ''
        self.canceled = False
        self.frame = tk.Frame(self)

        if message:
            self.label_msg = tk.Label(self.frame,
                                           text=message,
                                           fg='red')
        self.label_pw = tk.Label(
            self.frame,
            text='Please enter your encfs password'
            )
        self.entry = tk.Entry(self.frame, show='*')

        def getpassword():
            self.password = self.entry.get()
            self.destroy()

        self.button_ok = tk.Button(self.frame,
                                     text='OK',
                                     command=getpassword)

        def breakloop():
            self.canceled = True
            self.destroy()

        self.button_cancel = tk.Button(self.frame,
                                            text='Cancel',
                                            command=breakloop)

        # Pack Everything Up
        if message:
            self.label_msg.grid(row=0, columnspan=2)

        self.label_pw.grid(row=1, columnspan=2)
        self.entry.grid(row=2, columnspan=2)
        self.button_ok.grid(row=3, column=0)
        self.button_cancel.grid(row=3, column=1)

        self.entry.focus()
        self.frame.pack()

        self.bind('<Return>', lambda key: getpassword())
        self.focus_set()
        self.mainloop()


class Shell_Input():
    '''
    class to get password from the user using shell
    :Attr:
        * password (str) - the password entered by the user.
        * canceled (bool) - always False
    '''

    def __init__(self):
        self.password = getpass.getpass('Enter encfs password: ')
        self.canceled = False


def is_mounted(path):
    '''
    Test if the encfs mount path is in /etc/mtab.
    :Args:
        * path (str): absolute path to the encfs mount
    :Returns:
        * (bool): True = mounted, False = not-mounted
    '''
    mtab = open('/etc/mtab', 'r')
    mounted = False
    for line in mtab.readlines():
        if ('encfs' in line) and (path in line):
            mounted = True
    mtab.close()
    return mounted


def get_path(path):
    '''
    Converts user entered path to absolute path.
    :Args:
        path (str): user entered path such as '~/encfs/'
    :Returns:
        absolute_path (str): /home/user/endfs
    :Raises:
        OSError: if path does not exist.
    '''
    path = os.path.abspath(os.path.realpath(os.path.expanduser(path)))
    if os.path.isdir(path):
        return path
    else:
        raise OSError('\"{}\" does not exist'.format(path))


def run(crypt_path, mount_path, wrapped_prog):
    '''
    mounts encfs and starts another program. Waits until that program has
    terminated then unmounts the encfs mount point. Can be executed multiple
    times. In that case, the encfs filesystem will not unmount until all
    programs started by encfswrapper have terminated.
    :Args:
        * crypt_path (str): user entered path to the encrypted encfs data.
        * mount_path (str): user entered path to the encfs mountpoint
        * wrapped_progs (list): list of subprocess.Popen arguments to execute
          the external program.
    Example:
        run('~/.encfs', '~/encfs/', ['zim', '--standalone'])
    '''
    crypt_path = get_path(crypt_path)
    mount_path = get_path(mount_path)
    md5 = hashlib.md5()
    md5.update(mount_path.encode('utf-8'))
    tmppath = (md5.hexdigest())
    tmp = tempfile.gettempdir()
    lockdir = os.path.join(tmp, 'encfs-{}'.format(tmppath))

    # Check to see if the mount path is empty.
    if len(os.listdir(mount_path)) != 0:
        if not (is_mounted(mount_path)
                and os.path.isdir(lockdir)
                and (len(os.listdir(lockdir)) > 0)):
            msg = 'Mount Path \'{}\' is not empty'.format(mount_path)
            try:
                TkinterMsg(title='Mount Error',
                           message=msg)
            except:
                pass
            raise OSError(msg)

    try:
        bad_password = 1
        message = None
        canceled = False
        if not os.path.isdir(lockdir):
            os.mkdir(lockdir)
        lockfile = tempfile.mkstemp('', 'encfs', lockdir)

        if not is_mounted(mount_path):
            while (bad_password):
                try:
                    password = Tkinter_Input(message=message)
                except Exception:
                    password = Shell_Input()
                canceled = password.canceled
                if canceled:
                    break

                encfs = subprocess.Popen(
                    ['encfs', '--stdinpass',
                     crypt_path, mount_path],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE
                )
                message = encfs.communicate(
                    input=password.password.encode('utf-8')
                )[0].rstrip()
                bad_password = encfs.returncode

        if is_mounted(mount_path):
            subprocess.call(wrapped_prog)

    finally:
        # Give fuse a chance to finish mounting if wrapped_prog has a
        # very short run time or programs that close slowly
        time.sleep(.5)
        os.close(lockfile[0])
        os.remove(lockfile[1])

        if is_mounted(mount_path) and len(os.listdir(lockdir)) == 0:
            return_code = subprocess.call(['fusermount',
                                           '-u',
                                           mount_path])
            os.rmdir(lockdir)
            if return_code:
                msg = 'failed to unmount {}'.format(mount_path)
                try:
                    TkinterMsg(title='OSError',
                               message=msg)
                except:
                    pass
                raise OSError(msg)
            else:
                print('Successfully unmounted "{}"'.format(mount_path))


def main():
    '''
    cli interface.
    '''
    parser = argparse.ArgumentParser(
        description=('Mount an encfs filesystem while COMMAND runs.'
                     ' Automatically unmount the encfs filesystem after'
                     ' COMMAND terminates.'),
        usage='%(prog)s [-h] encfsDir mountPoint COMMAND [options...]'
    )
    parser.add_argument('encfsDir', nargs=1, help='encfs encrypted directory')
    parser.add_argument('mountPoint', nargs=1, help='encfs mount point')
    parser.add_argument('command',
                        metavar='COMMAND [options...]',
                        nargs=argparse.REMAINDER,
                        help='command to run including its arguments '
                             'and options.'
                        )
    args = parser.parse_args()
    run(args.encfsDir[0], args.mountPoint[0], args.command)


if __name__ == '__main__':
    main()