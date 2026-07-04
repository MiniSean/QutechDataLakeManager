How to install: (https://qutech-data-lake.gitlab.io/docs/latest/users/getting-started/installation.html#qdl-sdk-and-cli)

pip install qdl-sdk --index-url https://gitlab.com/api/v4/projects/66914457/packages/pypi/simple
pip install qdl-cli --index-url https://gitlab.com/api/v4/projects/66914457/packages/pypi/simple
pip install qdl-daemon --index-url https://gitlab.com/api/v4/projects/66914457/packages/pypi/simple
# QDL sync service
pip install qdl-sync-service --index-url https://gitlab.com/api/v4/projects/66914457/packages/pypi/simple
# QDL-specific QMI plugin (Failed for now because it requires python >=3.12 <3.14 and I am running a 3.11 environment. This might be a problem)
pip install qdl-qmi-plugin --index-url https://gitlab.com/api/v4/projects/66914457/packages/pypi/simple

# --- Setup notes

run daemon and sync-service in background using
$ qdl-daemon
and
$ qdl-sync-service

Navigate to ~/.qdl/
This should now contain config-sync-service.yaml (because we installed qdl-qmi-plugin)

Note: plugins/qmi/<VERSION>/ is still empty.
Download a plugin from (here)[https://gitlab.com/qutech-data-lake/plugins/-/packages/61251256] or construct a custom plugin.
Place plugin executable here  plugins/qmi/<VERSION>/bin/qdl-qmi-plugin.exe

Then we can configure the sync service as follows (example):
$ qdl sync create "qmi" "dicarlo-testing" D:/sean/programs/PyCharmProjects/QutechDataLakeManager/EmptyDataDirectory/ "0.3.0"
$ qdl sync create "custom" "dicarlo-testing" D:/sean/programs/PyCharmProjects/QutechDataLakeManager/EmptyDataDirectory/ "0.1.0"
```
The sync for QMI data source was created successfully
Sync service configuration:
sync interval:                                                             0.1s
Data source configuration:
scope uid:                                                      dicarlo-testing
type:                                                                       QMI
data location:             D:/sean/programs/PyCharmProjects/QutechDataLakeMana▒
status:                                                                disabled
version:                                                                  0.3.0
scan interval:                                                             2.0s

Enable the sync with the following command: qdl sync start
```

Start the plugin using:
$ qdl sync start

--- Plugin stops/starts successful
event="Sync-service: State manager state change: TERMINATED -> STARTING" level=info timestamp=2026-07-02T09:24:31.666086Z
event="Sync-service: Terminating plugin" level=info timestamp=2026-07-02T09:24:31.666086Z
event="Sync-service: Plugin stopped" level=info timestamp=2026-07-02T09:24:31.666086Z
event="Sync-service: Plugin C:\\Users\\SeanM\\.qdl\\plugins\\qmi\\0.3.0\\bin\\qdl-qmi-plugin.exe started successfully" level=info timestamp=2026-07-02T09:24:31.743609Z
event="Sync-service: State manager state change: STARTING -> WAITING_FOR_STARTED" level=info timestamp=2026-07-02T09:24:31.743609Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:24:31.879623Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:24:32.003638Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:24:32.127739Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:24:32.251757Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:24:32.375772Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:24:32.499685Z
event="QMI-plugin started" level=info timestamp=2026-07-02T09:24:32.622349Z
event="QMI-plugin: startup data ingest" level=info timestamp=2026-07-02T09:24:32.623089Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:24:32.622923Z
event="QMI-plugin: Published status" event_key=PLUGIN_HEARTBEAT_UPDATE level=info state=STARTED timestamp=2026-07-02T09:24:32.634286Z
---

Note: check qdl-sync-service window for 'healty' PLUGIN_HEARTBEAT_UPDATE logs.

Next we copy a measurement data into the monitored directory to see how the sync-service handles it.
The new directory structure looks as follows:
```
EmptyDataDirectory/
  └── 20260601
      └── 20260601-194952-669-55d709-SIM_surface_code_ZXXZ_Z_type
      └── 20260601-195216-105-71a69c-SIM_surface_code_ZXXZ_X_type
      └── 20260601-195437-851-9a75a0-SIM_surface_code_Z_type
      └── 20260601-195649-390-780513-SIM_surface_code_X_type
```

--- LOG timeline when uploading measurement data to the EmptyDataDirectory/ which is monitored by the sync service:

event="QMI-plugin: Published status" event_key=PLUGIN_HEARTBEAT_UPDATE level=info state=HEALTHY timestamp=2026-07-02T09:31:03.000862Z
event="Sync-service: work" func_name=work level=debug lineno=227 module=worker process_name=MainProcess thread_name=MainThread timestamp=2026-07-02T09:31:03.001083Z
event="Sync-service: Received published heartbeat" event_key=PLUGIN_HEARTBEAT_UPDATE level=info state=HEALTHY timestamp=2026-07-02T09:31:03.001083Z

---

event="QMI-plugin: Datafile checksum calculation failed: Checksum error: Exception when opening file D:\\sean\\programs\\PyCharmProjects\\QutechDataLakeManager\\EmptyDataDirectory\\20260601\\20260601-194952-669-55d709-SIM_surface_code_ZXXZ_Z_type\\dataset.hdf5: [Errno 13] Permission denied: 'D:\\\\sean\\\\programs\\\\PyCharmProjects\\\\QutechDataLakeManager\\\\EmptyDataDirectory\\\\20260601\\\\20260601-194952-669-55d709-SIM_surface_code_ZXXZ_Z_type\\\\dataset.hdf5'" event_key=PLUGIN_SCAN_DATASETS level=error timestamp=2026-07-02T09:31:06.642209Z
event="QMI-plugin: error while scanning data store: [Errno 13] Unable to synchronously open file (unable to open file: name = 'D:\\sean\\programs\\PyCharmProjects\\QutechDataLakeManager\\EmptyDataDirectory\\20260601\\20260601-194952-669-55d709-SIM_surface_code_ZXXZ_Z_type\\dataset.hdf5', errno = 13, error message = 'Permission denied', flags = 0, o_flags = 0)" event_key=PLUGIN_SCAN_DATASETS level=error timestamp=2026-07-02T09:31:06.642931Z

---

event="QMI-plugin: Published status" event_key=PLUGIN_HEARTBEAT_UPDATE level=info state=FAILED timestamp=2026-07-02T09:31:13.010937Z
event="Sync-service: Received published heartbeat" event_key=PLUGIN_HEARTBEAT_UPDATE level=info state=FAILED timestamp=2026-07-02T09:31:13.011166Z

# --- How to build the custom plugin
$ python custom_qdl_plugin/build.py

# --- How to build the client program
$ python client/build_client.py


# ---

To answer your question: No, it's not creating subprocesses. It's creating thousands of short-lived HTTP connections that get stuck in the TIME_WAIT state.

Should we go back to Batched Processing?
You don't necessarily have to go back to batched processing, but you do need to introduce some form of pacing to avoid overwhelming the network stack. Here are the two best approaches:

Option 1: Add flow control to your "one-by-one" tactic (Recommended) You can keep the one-by-one processing, but the plugin must respect backpressure. Instead of sending all 7195 requests in a tight loop, the plugin should send one dataset, wait to receive the data_file_ready_response from the sync-service, and only then send the next dataset. This will naturally pace the sync-service so it doesn't exceed the OS's ability to recycle ports.

You would need to modify main.py in your plugin to track an ongoing request and wait for the ack in receive_loop before scan_loop proceeds.

Option 2: Go back to batched processing If batched processing means sending a single payload with multiple datasets (and the sync-service/daemon process them in a single bulk API call), this would drastically reduce the number of HTTP connections opened, solving the port exhaustion.

Option 3: Connection Pooling (If you control the sync-service) If you are the developer of the sync-service and the qdl library, the best network-level fix is to ensure the QDL python library uses a connection pool (e.g., a shared httpx.AsyncClient or requests.Session). This reuses a single TCP connection for all requests to port 5500, completely eliminating TIME_WAIT buildup.

Let me know if you'd like me to help implement the flow control in the plugin's main.py or take a different route!