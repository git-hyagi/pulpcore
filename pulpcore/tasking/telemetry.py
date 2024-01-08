import os
import sys
import time

from abc import abstractmethod
from django.utils import timezone
from opentelemetry import metrics
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

PULP_OTEL_ENABLED = bool(os.environ.get("PULP_OTEL_ENABLED",False))

# OPENTELEMETRY COLLECTOR/PROMETHEUS ENDPOINT URL
OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT","http://localhost:4318/v1/metrics")

# OPENTELEMETRY METRIC EXPORT INTERVAL
OTEL_METRIC_EXPORT_INTERVAL = int(os.environ.get("OTEL_METRIC_EXPORT_INTERVAL",5000))

# INTERVAL BETWEEN EACH METRIC COLLECTION
METRICS_POOL_INTERVAL = int(os.environ.get("METRIC_POOL_INTERVAL",1))

class TaskMetrics:
  # the meter attribute should be the same for all task metric instances
  meter = None

  def __init__(self):
    if TaskMetrics.meter is None:
       self._setup_meter()

  def _setup_meter(self):
       resource = Resource(attributes={SERVICE_NAME: "pulp-worker"})
       reader = PeriodicExportingMetricReader(
         OTLPMetricExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT),
         export_interval_millis=OTEL_METRIC_EXPORT_INTERVAL
       )
       meterProvider = MeterProvider(resource=resource, metric_readers=[reader])
       metrics.set_meter_provider(meterProvider)
       TaskMetrics.meter = metrics.get_meter("pulpcore.task")

  @abstractmethod
  def store_metric(self,task,time_spent,previous_state):
    pass

class WaitingMetric(TaskMetrics):

  # we can have only a single instance of "task.waiting" metric
  wait_metric = None
  def __init__(self):
    super().__init__()
    if self.wait_metric is None:
      self.wait_metric = self.meter.create_counter(
        name = "task.waiting",
        description= "amount of time from a task being created until it is Running/Canceled",
        unit = "s",
      )

  def store_metric(self,task,time_spent,previous_state=None):
    self.wait_metric.add(
      time_spent,
      {"task.name": task.name,
       "task.previous_state": "n/a",
       "task.state": "waiting",
       "task.uuid": str(task.pulp_id),
       "task.worker": task.worker.name,
      }
    )

class RunningMetric(TaskMetrics):
  # we can have only a single instance of "task.service" metric
  running_metric = None
  def __init__(self):
    super().__init__()
    if self.running_metric is None:
      self.running_metric = self.meter.create_counter(
        name = "task.service",
        description= "amount of time a task started Running until it is Finished/Canceled/Errored",
        unit = "s",
      )

  def store_metric(self, task,time_spent,previous_state):
    self.running_metric.add(
      time_spent,
      {"task.name": task.name,
       "task.previous_state": previous_state,
       "task.state": "running",
       "task.uuid": str(task.pulp_id),
       "task.worker": task.worker.name,
      }
    )

waiting_metric = WaitingMetric()
running_metric = RunningMetric()

def make_measurement(task,previous_state=None):
  current_state = task.state
  last_check = timezone.now()
  time_spent = 0.0
  while current_state == task.state:
    metric_method = getattr(sys.modules[__name__], task.state+"_metric")
    metric_method.store_metric(task,time_spent,previous_state)
    time.sleep(METRICS_POOL_INTERVAL)
    task.refresh_from_db(fields=["state"])
    time_spent = (timezone.now() - last_check).total_seconds()
    last_check = timezone.now()
