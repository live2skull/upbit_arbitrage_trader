# Generated by Django 2.2.6 on 2019-10-20 15:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ProfitResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, editable=False, primary_key=True, serialize=False)),
                ('balance', models.DecimalField(decimal_places=8, max_digits=20)),
                ('profit', models.DecimalField(decimal_places=8, max_digits=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ProfitResultTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, editable=False, primary_key=True, serialize=False)),
                ('market', models.CharField(max_length=16, null=True)),
                ('transaction_type', models.SmallIntegerField(choices=[(0, 'BUY'), (1, 'SELL')], null=True)),
                ('profit_result', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='unsterblich.ProfitResult')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
