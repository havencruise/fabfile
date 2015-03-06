import os.path
from datetime import datetime

from fabric.api import sudo, env
from fabric.context_managers import prefix, cd, settings
from fabric.contrib import files
from fabric.operations import run
from fabric.utils import abort

from fabutils import create_directories, puts, activate_venv, check_on_path

"""
Functions in this file are discrete steps that a the main fabfile may
call.
"""

def create_virtualenv(venv_path, user, permissions='0750'):
    "Creates a virtualenv"
    check_on_path('virtualenv')
    
    if not files.exists(os.path.join(venv_path, "bin/activate")):
        create_directories(venv_path, user, permissions)
        puts(info='Creating virtualenv at %s' % venv_path)
        env.run("virtualenv --no-site-packages %s" % venv_path)
        puts(success='virtualenv created')
        return 1
    else:
        puts(info='virtualenv already exists at %s' % venv_path)

def install_pip_dependencies(requirements_path):
    """
    Install dependencies using pip from the specified requirements file
    """
    puts(info='Installing dependencies with pip')

    with prefix(activate_venv()):
        env.run('pip install -r %s' % requirements_path)

    puts(success="Dependencies installed")

def django_syncdb(project_dir, production=False):
    """
    Sets up the database by running django's syncdb command

    @param project_dir The directory containing manage.py
    @param production Whether to use production settings
    """
    puts(info="Running syncdb")
    _settings_mod = ""
    if production: 
        _settings_mod = "--settings=settings_production"

    with prefix(activate_venv()):
        env.run(os.path.join(project_dir, 'manage.py') + 
            " syncdb %s" % _settings_mod)

    puts(success='Database synced')

def django_sync_and_migrate(project_dir, production=False):
    """
    Sets up the database by running django's syncdb command with
    --noinput and --migrate

    @param project_dir The directory containing manage.py
    @param production Whether to use production settings
    """
    puts(info="Running syncdb with --migrate")

    _settings_mod = ""
    if production: 
        _settings_mod = "--settings=settings_production"

    with prefix(activate_venv()):
        env.run(os.path.join(project_dir, 'manage.py') + 
            " syncdb --migrate --noinput %s" % _settings_mod)

    puts(success='Database synced')

def django_load_fixture(project_dir, path):
    """
    Load fixtures from a specific location

    @param project_dir The directory containing manage.py
    @param production The path to the fixture file to load
    """
    puts(info="Loading fixture at %s" % path)

    full_path = os.path.join(project_dir, path)

    if not files.exists(full_path):
        puts(error='Fixture file %s not found' % full_path)

    with prefix(activate_venv()):
        env.run(os.path.join(project_dir, 'manage.py') + " loaddata " + full_path)

    puts(success='Fixture loaded')

def django_migrate_schema(project_dir, production=False):
    """
    Migrates the database schema

    @param project_dir The directory containing manage.py
    @param production Whether to use production settings
    """
    puts(info="Applying migrations")

    _settings_mod = ""
    if production: 
        _settings_mod = "--settings=settings_production"
    with prefix(activate_venv()):
        env.run(os.path.join(project_dir, 'manage.py') + 
                " migrate --all %s" % _settings_mod)

    puts(success="Migrations applied")

def django_publish_static_content(project_dir, production=False):
    """
    Collects django's static content and publishes it to the static directory.

    @param project_dir The directory containing manage.py
    @param production Whether to use production settings
    """
    puts(info="Collecting static content")
    _settings_mod = ""
    if production: 
        _settings_mod = "--settings=settings_production"
    with prefix(activate_venv()):
        env.run(os.path.join(project_dir, 'manage.py') +
            ' collectstatic --noinput %s' % _settings_mod)

    puts(success="Static content published")

def git_clone(repo_path, destination, user):
    """
    Clone the git repository at repo_path to destination.

    If destination doesn't exist, it will be created and owned by user.
    """
    check_on_path('git')

    puts(info="Cloning git repository %s into %s" % (repo_path, destination))

    with settings(warn_only=True):
        if env.run("test -d %s" % destination).failed:
            puts(info="Creating destination directory %s" % destination)
            create_directories(destination, user)
            puts(success="Destination directory created")

    env.run('git clone %s %s' % (repo_path, destination))
    puts(success="Repository cloned")

def git_pull(destination):
    """
    Update the git repository at destination.
    """
    check_on_path('git')

    puts(info="Updating git repository in %s" % destination)

    if env.run("test -d %s" % destination).succeeded:
        with cd(destination):
            env.run('git pull')
            puts(success="Repository updated")
    else:
        puts(error="Unable to pull - destination directory doesn't exist")
        abort("Aborting")

def git_init_submodules(git_path):
    """
    Initialise and update git submodules
    """
    check_on_path('git')
    
    puts(info="Initialising git submodules")
    with cd(git_path):
        env.run('git submodule update --init')
    puts(success="Submodules initialised")

def compile_less_css(project_dir):
    """
    Compiles less files to css
    """
    puts(info="Compiling LESS to css")
    if files.exists(os.path.join(project_dir, "plessc.py")):
        with cd(project_dir):
            with prefix(activate_venv()):
                env.run('./plessc.py')
                puts(success="Stylesheets compiled")
    else:
        puts(info="plessc.py not found - skipping")

def conditionally_install_and_patch_pil(requirements_file_path, venv_dir,
        patch_path):
    """
    PIL's setup.py file needs to be patched on centos to enable JPEG and
    PNG support.

    It will check whether PIL is in the requirements file and if so
    install it and patch it outside of pip's automated system.

    @param requirements_file_path Path to pip's requirements file
    @param venv_dir Path to the virtualenv directory
    @param patch_path Path to the patch file to apply
    """
    if files.contains(requirements_file_path, 'PIL'):
        puts(info="Installing PIL")
        pil_version = env.run('grep PIL %s' % requirements_file_path)

        with prefix(activate_venv()):
            env.run('pip install -I %s --no-install' % pil_version)
            # patch setup.py
            env.run('patch --unified %s %s' % (os.path.join(venv_dir,
                'build', 'PIL', 'setup.py'), patch_path))
            env.run('pip install -I %s --no-download'  % pil_version)

        puts(success="PIL patched and installed")
    else:
        puts(info="PIL doesn't need to be installed")

def backup_database(project_name, project_dir, destination_dir):
    """
    Backs-up the database
    """
    dump_file = "%s-prod-%s.sql" % (project_name,
        datetime.now().strftime('%Y%m%d_%H%M%S'))

    temp_dump_path = os.path.join('/tmp', dump_file)

    puts(info="Backing up database")

    with prefix(activate_venv()):
        with cd(project_dir):
            DATABASE_USER = env.run("python -c 'import settings_production;"
                "print settings_production.DATABASES[\"default\"][\"USER\"]'")
            DATABASE_PASSWORD = env.run("python -c 'import settings_production;"
                "print settings_production.DATABASES[\"default\"][\"PASSWORD\"]'")
            DATABASE_NAME = env.run("python -c 'import settings_production;"
                "print settings_production.DATABASES[\"default\"][\"NAME\"]'")

    env.run('unset HISTFILE && mysqldump -u %s -p%s %s > %s' % (
        DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME, temp_dump_path))
    puts(success="Database backed up to %s" % temp_dump_path)

    puts(info="Compressing database backup")
    env.run('bzip2 %s' % temp_dump_path)
    temp_dump_path += '.bz2'
    puts(success="Database backup compressed")

    puts(info="Moving backup to %s" % destination_dir)
    with settings(warn_only=True):
        if sudo("test -d %s" % destination_dir).failed:
            puts(info="Creating destination directory %s" % destination_dir)
            create_directories(destination_dir, 'root')
            puts(success="Destination directory created")
    sudo('mv %s %s' % (temp_dump_path, destination_dir))
    puts(success="Database moved to %s" % destination_dir)

def roll_site_forward(deployment_dir):
    """
    Updates the symlinks to point to a later timestamped version of the
    project.
    """
    newest_deployment = env.run('ls -1 %s | grep 2 | tail -n 1' % deployment_dir)
    
    # unlink previous deployment and link the newest one as 'live'
    with cd(deployment_dir):
        with settings(warn_only=True):
            env.run('unlink live')
        env.run('ln -s %s live' % (newest_deployment))
        puts(success="Symlink rolled forward")

def restart_services():
    """
    Restarts/reloads gunicorn, nginx and memcached
    """
    check_on_path('supervisorctl')
    
    # restart all processes controlled by supervisord
    sudo('supervisorctl restart all')

    # restart nginx
    sudo('/etc/init.d/nginx restart')
    
    # restart memcached
    sudo('/etc/init.d/memcached restart')

def prune_directory(directory, pattern, max_entries):
    """
    Deletes all but the last `max_entries` number of directories (when
    sorted in name order) that match `pattern` in `directory`

    @param string directory Directory to prune inside
    @param string pattern A pattern to pass to grep to restrict the list of
        files/directories that will be pruned
    @param int max_entries The maximum number of files/directories that
        should be retained in `directory`
    """
    with settings(warn_only=True):
        puts(info="Pruning %s to contain no more than %d files that match %s" %
            (directory, max_entries, pattern))
        if env.run('ls -1r %s | grep %s | tail -n +%d | xargs rm -rf --preserve-root'
            % (directory, pattern, max_entries)).succeeded:
            puts(success="%s pruned" % directory)