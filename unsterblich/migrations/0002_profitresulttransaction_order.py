# Generated by Django 2.2.6 on 2019-10-20 15:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unsterblich', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='profitresulttransaction',
            name='order',
            field=models.SmallIntegerField(null=True),
        ),
    ]
