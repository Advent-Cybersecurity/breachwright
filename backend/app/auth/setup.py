"""First-run setup: create initial admin account.
Usage:
    breachwright --setup
"""
import asyncio
import getpass
import os
import sys


def run_migrations():
    """Run Alembic migrations to ensure tables exist."""
    from alembic.config import Config as AlembicConfig
    from alembic import command
    from app.config import settings
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        alembic_ini = os.path.join(sys._MEIPASS, "backend", "alembic.ini")
        alembic_dir = os.path.join(sys._MEIPASS, "backend", "alembic")
    else:
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        alembic_ini = os.path.join(backend_dir, "alembic.ini")
        alembic_dir = os.path.join(backend_dir, "alembic")
    alembic_cfg = AlembicConfig(alembic_ini)
    alembic_cfg.set_main_option("sqlalchemy.url", settings.resolved_database_url)
    alembic_cfg.set_main_option("script_location", alembic_dir)
    command.upgrade(alembic_cfg, "head")


def _has_stdin():
    """Check if stdin is available (not available in GUI-only exe on Windows)."""
    try:
        if sys.stdin is None:
            return False
        return sys.stdin.readable()
    except Exception:
        return False


def _gui_setup_dialog():
    """Fallback setup dialog using tkinter when no terminal is available."""
    import tkinter as tk
    from tkinter import messagebox

    result = {}

    def submit():
        email = email_var.get().strip()
        name = name_var.get().strip() or email.split("@")[0]
        pw = pw_var.get()
        pw2 = pw2_var.get()

        if not email:
            messagebox.showerror("Error", "Email is required.")
            return
        if pw != pw2:
            messagebox.showerror("Error", "Passwords do not match.")
            return
        if len(pw) < 8:
            messagebox.showerror("Error", "Password must be at least 8 characters.")
            return

        result["email"] = email
        result["display_name"] = name
        result["password"] = pw
        root.destroy()

    root = tk.Tk()
    root.title("Breachwright - First Run Setup")
    root.geometry("400x320")
    root.resizable(False, False)
    root.configure(bg="#0a0a0f")

    tk.Label(root, text="BREACHWRIGHT SETUP", font=("Consolas", 14, "bold"),
             fg="#ef4444", bg="#0a0a0f").pack(pady=(20, 5))
    tk.Label(root, text="Create your admin account", font=("Consolas", 9),
             fg="#a0a0a0", bg="#0a0a0f").pack(pady=(0, 15))

    frame = tk.Frame(root, bg="#0a0a0f")
    frame.pack(padx=30, fill="x")

    tk.Label(frame, text="Email:", fg="#cccccc", bg="#0a0a0f", anchor="w").pack(fill="x")
    email_var = tk.StringVar()
    tk.Entry(frame, textvariable=email_var, bg="#1a1a25", fg="white",
             insertbackground="white", relief="flat", font=("Consolas", 10)).pack(fill="x", pady=(0, 8))

    tk.Label(frame, text="Display Name:", fg="#cccccc", bg="#0a0a0f", anchor="w").pack(fill="x")
    name_var = tk.StringVar()
    tk.Entry(frame, textvariable=name_var, bg="#1a1a25", fg="white",
             insertbackground="white", relief="flat", font=("Consolas", 10)).pack(fill="x", pady=(0, 8))

    tk.Label(frame, text="Password:", fg="#cccccc", bg="#0a0a0f", anchor="w").pack(fill="x")
    pw_var = tk.StringVar()
    tk.Entry(frame, textvariable=pw_var, show="*", bg="#1a1a25", fg="white",
             insertbackground="white", relief="flat", font=("Consolas", 10)).pack(fill="x", pady=(0, 8))

    tk.Label(frame, text="Confirm Password:", fg="#cccccc", bg="#0a0a0f", anchor="w").pack(fill="x")
    pw2_var = tk.StringVar()
    tk.Entry(frame, textvariable=pw2_var, show="*", bg="#1a1a25", fg="white",
             insertbackground="white", relief="flat", font=("Consolas", 10)).pack(fill="x", pady=(0, 15))

    tk.Button(frame, text="Create Admin Account", command=submit,
              bg="#ef4444", fg="white", relief="flat", font=("Consolas", 10, "bold"),
              activebackground="#dc2626", cursor="hand2").pack(fill="x", ipady=4)

    root.mainloop()
    return result if result else None


async def create_admin():
    from sqlalchemy import select, func
    from app.db.session import async_session
    from app.auth.models import User, UserRole
    from app.auth.service import hash_password
    async with async_session() as db:
        result = await db.execute(select(func.count(User.id)))
        count = result.scalar_one()
        if count > 0:
            if _has_stdin():
                print(f"  Setup already complete ({count} user(s) exist).")
                print("  Use the app to manage additional users.")
            else:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo("Breachwright", f"Setup already complete ({count} user(s) exist).\nUse the app to manage additional users.")
                root.destroy()
            sys.exit(0)

        if _has_stdin():
            print()
            print("  ╔══════════════════════════════════════════════╗")
            print("  ║       BREACHWRIGHT - First Run Setup         ║")
            print("  ║      An Advent Cybersecurity Product          ║")
            print("  ╚══════════════════════════════════════════════╝")
            print()
            email = input("  Admin email: ").strip()
            if not email:
                print("  Email is required.")
                sys.exit(1)
            display_name = input("  Display name: ").strip() or email.split("@")[0]
            password = getpass.getpass("  Password: ")
            confirm = getpass.getpass("  Confirm password: ")
            if password != confirm:
                print("  Passwords do not match.")
                sys.exit(1)
            if len(password) < 8:
                print("  Password must be at least 8 characters.")
                sys.exit(1)
        else:
            creds = _gui_setup_dialog()
            if not creds:
                sys.exit(1)
            email = creds["email"]
            display_name = creds["display_name"]
            password = creds["password"]

        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            role=UserRole.admin,
        )
        db.add(user)
        await db.commit()

        if _has_stdin():
            print()
            print(f"  Admin account created: {email}")
            print("  Launch Breachwright to log in.")
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("Breachwright", f"Admin account created: {email}\nLaunch Breachwright to log in.")
            root.destroy()


def setup():
    """Run migrations (sync), then create admin (async)."""
    if _has_stdin():
        print("  Initializing database...")
    run_migrations()
    if _has_stdin():
        print("  Database ready.")
    asyncio.run(create_admin())


if __name__ == "__main__":
    setup()
