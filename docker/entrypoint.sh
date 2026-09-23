#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py seed
python manage.py shell -c "
from django.contrib.auth import get_user_model
U = get_user_model()
if not U.objects.filter(username='admin').exists():
    U.objects.create_superuser('admin', 'admin@example.org', 'admin')
    print('Created staff login admin / admin')
"

exec "$@"
