import os
import datetime
from peewee import Model, CharField, DateTimeField, AutoField
from app.db.models import db

class UserModel(Model):
    class Meta:
        database = db
        table_name = "users"

    id = AutoField()
    username = CharField(unique=True, max_length=64)
    hashed_password = CharField()
    created_at = DateTimeField(default=datetime.datetime.utcnow)

def init_user_table():
    with db:
        db.create_tables([UserModel], safe=True)
