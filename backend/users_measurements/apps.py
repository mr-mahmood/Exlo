from django.apps import AppConfig


class UsersMeasurementsConfig(AppConfig):
    name = "users_measurements"

    def ready(self):
        import users_measurements.signals
