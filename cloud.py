"""Синхронизация с облаком через REST API (Firebase Realtime Database).

Адрес базы: https://<project>-default-rtdb.firebaseio.com
Операции лежат в узле /transactions.json. Подходит и любой другой REST-сервис,
который принимает GET/PUT с JSON на тот же путь.
"""
import json
import urllib.error
import urllib.request


class CloudError(Exception):
    pass


class CloudSync:
    def __init__(self, base_url, token="", timeout=10):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.token = (token or "").strip()
        self.timeout = timeout

    def _endpoint(self):
        if not self.base_url:
            raise CloudError("Укажите адрес облака в настройках")
        url = f"{self.base_url}/transactions.json"
        if self.token:
            url += f"?auth={self.token}"
        return url

    def _request(self, method, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._endpoint(), data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as e:
            raise CloudError(f"Сервер ответил {e.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise CloudError(f"Нет связи с облаком: {getattr(e, 'reason', e)}")
        except ValueError:
            raise CloudError("Сервер вернул не JSON")

    def sync(self, ledger):
        """Двусторонняя синхронизация. Возвращает (получено, всего_в_облаке)."""
        remote = self._request("GET") or {}
        received = ledger.merge(remote)
        merged = ledger.as_payload()
        self._request("PUT", merged)
        return received, len(merged)
