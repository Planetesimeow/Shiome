"""Operator recovery: run in the app container; passwords are prompted, never arguments."""
import argparse
from getpass import getpass

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description='Reset an existing Shiome login and invalidate its sessions')
    parser.add_argument('username')
    args = parser.parse_args()
    load_dotenv()
    from app.identity import connection, password_digest
    password = getpass('New password (12-128 characters): ')
    if password != getpass('Repeat password: '):
        raise SystemExit('Passwords do not match')
    digest = password_digest(password)
    with connection() as conn:
        result = conn.execute('UPDATE users SET password_hash=?,session_version=session_version+1 '
                              'WHERE username=? COLLATE NOCASE', (digest, args.username.strip()))
        if result.rowcount != 1:
            raise SystemExit('User not found')
    print('Password updated; previous sessions are no longer valid.')


if __name__ == '__main__':
    main()
