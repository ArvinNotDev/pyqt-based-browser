
import json
import requests

def check_connectivity(timeout=5):
    try:
        requests.head("https://www.google.com", timeout=timeout)
        print("heeeey")
        return True
    except requests.RequestException:
        print("hey")
        return False
    except Exception as e:
        print(e)


def what_is_my_ip(proxy=None, timeout=10, cancel_event=None):
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Exit-IP check was cancelled.")

    url = "https://api.ipify.org?format=json"
    proxies = {"http": proxy, "https": proxy} if proxy else None
    response = None
    try:
        # Stream the small response so the shared shutdown token can close its
        # socket while the request is waiting for an unavailable Tor route.
        response = requests.get(url, proxies=proxies, timeout=timeout, stream=True)
        register = getattr(cancel_event, "register_response", None)
        if callable(register):
            register(response)
        elif cancel_event is not None and cancel_event.is_set():
            response.close()
            raise InterruptedError("Exit-IP check was cancelled.")
        response.raise_for_status()
        chunks = []
        for chunk in response.iter_content(chunk_size=4096):
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Exit-IP check was cancelled.")
            if chunk:
                chunks.append(chunk)
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Exit-IP check was cancelled.")
        return json.loads(b"".join(chunks).decode("utf-8")).get("ip")
    except requests.RequestException as exc:
        raise Exception(f"Error: {exc}") from exc
    finally:
        if response is not None:
            response.close()
