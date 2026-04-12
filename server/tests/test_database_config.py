from types import SimpleNamespace

from app.core import database


def test_get_database_url_prefers_explicit_database_url(monkeypatch):
    settings = SimpleNamespace(
        database_url="postgresql+psycopg2://explicit:secret@db.example.com:5432/app",
        nacos_datasource_data_id="agent-datasource.yml",
        nacos_group="DEFAULT_GROUP",
        nacos_namespace="dev",
    )

    monkeypatch.setattr(database, "get_settings", lambda: settings)

    class FailIfCalled:
        def get_yaml_config(self, **_kwargs):
            raise AssertionError("nacos should not be called when DATABASE_URL is set")

    monkeypatch.setattr(database, "get_nacos_client", lambda: FailIfCalled())

    assert database.get_database_url() == settings.database_url


def test_get_database_url_loads_postgres_url_from_nacos(monkeypatch):
    settings = SimpleNamespace(
        database_url="sqlite:///./coagent.db",
        nacos_datasource_data_id="agent-datasource.yml",
        nacos_group="DEFAULT_GROUP",
        nacos_namespace="dev",
    )

    monkeypatch.setattr(database, "get_settings", lambda: settings)

    class FakeNacosClient:
        def get_yaml_config(self, **_kwargs):
            return {
                "spring": {
                    "datasource": {
                        "url": "jdbc:postgresql://127.0.0.1:15432/financial_coagent_phase1",
                        "username": "postgres",
                        "password": "p@ss word",
                    }
                }
            }

    monkeypatch.setattr(database, "get_nacos_client", lambda: FakeNacosClient())

    assert (
        database.get_database_url()
        == "postgresql+psycopg2://postgres:p%40ss+word@127.0.0.1:15432/financial_coagent_phase1"
    )
