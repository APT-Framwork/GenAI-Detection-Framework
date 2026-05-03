from django.db import models

# Create your models here.

class Workspaces(models.Model):
    user_id = models.IntegerField()
    name = models.TextField()
    domain_name = models.TextField(null=True)
    domain_user = models.TextField(null=True)
    user_password = models.TextField(null=True)



class Activity(models.Model):
    user_id = models.IntegerField()
    workspace_id = models.IntegerField()
    type = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    begin_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True)
    results = models.JSONField(null=True)
    traces = models.TextField(null=True)

class Scenario(models.Model):
    user_id = models.IntegerField()
    workspace_id = models.IntegerField()
    scenario_name = models.CharField(max_length=100)
    scenario_steps = models.JSONField(null=True)