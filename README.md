# -Terralogic-Hackathon-Project
# 🚀 Django Project — Setup & Run (using Pipenv)

A straight-to-the-point README for getting this Django project up and running with the `Pipfile` (Pipenv). No fluff — just the commands and notes you need.

---

## Prereqs

* **Python 3.8+** (Python 3.12 is fine — check project's `Pipfile` if you need a specific version)
* **pipenv** installed globally

Install pipenv if you don't have it:

```bash
pip install --user pipenv
# or
pip install pipenv
```

---

## Quick setup (dev) — 7 steps

1. Clone repo (if not already):

```bash
git clone https://github.com/your-username/your-project.git
cd your-project
```

2. Install dependencies from `Pipfile` (creates virtualenv + installs packages):

```bash
pipenv install
# if you want dev-packages too:
# pipenv install --dev
```

3. Activate the virtualenv shell (optional but handy):

```bash
pipenv shell
```

> Alternative: run one-off commands without activating the shell using `pipenv run ...` (example below).

4. Create environment variables file (recommended):

Create a `.env` at project root and add keys your Django app needs. Example:

```
DEBUG=True
SECRET_KEY=your-secret-key-here
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3  # or your postgres URL
```

Many Django setups use `django-environ` or `python-dotenv` to load `.env`. If not present, set variables directly in your shell.

5. Database migrations:

If you activated shell:

```bash
python manage.py migrate
```

If you didn't activate shell:

```bash
pipenv run python manage.py migrate
```

6. Create a superuser (admin):

```bash
python manage.py createsuperuser
# or
pipenv run python manage.py createsuperuser
```

7. Run the dev server:

```bash
python manage.py runserver 0.0.0.0:8000
# or
pipenv run python manage.py runserver 0.0.0.0:8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) (or your host/port) in your browser.

---

## Common commands cheat-sheet

Use `pipenv shell` first, otherwise prefix with `pipenv run`.

* Install a new dependency:

  * `pipenv install <package>`
* Install a development-only dependency:

  * `pipenv install --dev <package>`
* Uninstall a package:

  * `pipenv uninstall <package>`
* Run Django management command without opening shell:

  * `pipenv run python manage.py <command>`
* Run tests:

  * `pipenv run pytest`  (or `pipenv run python manage.py test` depending on test setup)
* Check the lockfile (reproducible builds):

  * `pipenv lock --clear`

---

## Static files (production-ish workflow)

When deploying or testing static file handling locally:

```bash
python manage.py collectstatic --noinput
```

Make sure `STATIC_ROOT` is set in `settings.py` (or via env var).

---

## Running without `pipenv shell`

You can avoid entering the shell by prefixing commands with `pipenv run`.

Examples:

```bash
pipenv run python manage.py migrate
pipenv run python manage.py runserver
pipenv run gunicorn your_project.wsgi:application
```

---

## Production notes (short and real)

* Use a proper WSGI server: **gunicorn** (behind **nginx**). Example:

```bash
pipenv run gunicorn your_project.wsgi:application --workers 3 --bind 0.0.0.0:8000
```

* Use a real DB (Postgres), not SQLite. Set `DATABASE_URL` in env.
* Ensure `DEBUG=False` and `SECRET_KEY` is secret.
* Configure `ALLOWED_HOSTS` and HTTPS (nginx + certbot).
* Use a process manager (systemd / supervisor) to keep gunicorn alive.

---

## Troubleshooting — quick hits

* `ModuleNotFoundError` after activating venv? Run `pipenv install` again.
* `django.core.exceptions.ImproperlyConfigured: SECRET_KEY` — make sure `.env` is present or env var is set.
* Port in use when `runserver` fails — change port: `runserver 0.0.0.0:8001`.
* Migrations complaining about conflicts — run `python manage.py makemigrations` then `migrate`.

---

## Extra tips (pro dev moves)

* Use `pipenv --venv` to find where the virtualenv lives.
* Keep secrets out of git. Add `.env` to `.gitignore`.
* Pin packages by committing `Pipfile.lock` to repo.
* Use `pipenv graph` to inspect dependency tree.

---
