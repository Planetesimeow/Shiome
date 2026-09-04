"""
生成 SHIOME_PASSWORD_HASH，贴进 .env 就行。

    python -m scripts.set_password

口令从终端读（不回显），只打印哈希 —— 明文口令不会出现在命令历史或输出里。
顺便生成一个 SHIOME_SECRET_KEY：设了它，改口令时已登录的会话不会被踢掉。
"""
import getpass
import secrets

from app.auth import hash_password


def main():
    pw = getpass.getpass("设置口令：")
    if len(pw) < 8:
        raise SystemExit("口令太短了（至少 8 位）。这是要挂到公网上的东西。")
    if pw != getpass.getpass("再输一次："):
        raise SystemExit("两次输入不一致。")

    print("\n把下面两行加进 .env：\n")
    print(f"SHIOME_PASSWORD_HASH={hash_password(pw)}")
    print(f"SHIOME_SECRET_KEY={secrets.token_hex(32)}")
    print("\n给脚本/手机快捷指令直接调接口用的 token（可选）：\n")
    print(f"SHIOME_API_TOKEN={secrets.token_urlsafe(32)}")


if __name__ == "__main__":
    main()
