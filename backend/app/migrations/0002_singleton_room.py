from django.db import migrations


def create_singleton_room(apps, schema_editor):
    GameRoom = apps.get_model('app', 'GameRoom')
    GameRoom.objects.update_or_create(pk=1, defaults={'name': 'arena', 'status': 'waiting'})


def delete_singleton_room(apps, schema_editor):
    GameRoom = apps.get_model('app', 'GameRoom')
    GameRoom.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_singleton_room, delete_singleton_room),
    ]
