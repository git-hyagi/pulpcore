# we should create a new Process to handle each metric to avoid impacting the
# app core execution
import os
import sys

from opentelemetry import metrics
from django.utils import timezone
from opentelemetry.util.types import Attributes
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from pulpcore.constants import TASK_STATES

class TaskMetrics:
  # the meter attribute should be the same for all task metric instances
  meter = None

  def __init__(self):
    if TaskMetrics.meter is None:
       self._setup_meter()

  def _setup_meter(self):
       endpoint = os.environ.get("OTEL_METRIC_ENDPOINT_URL","http://localhost:4318/v1/metrics")
       export_interval = os.environ.get("OTEL_EXPORT_INTERVAL",1000)

       resource = Resource(attributes={SERVICE_NAME: "pulp-worker"})
       reader = PeriodicExportingMetricReader(
         OTLPMetricExporter(endpoint=endpoint),
         export_interval_millis=export_interval
       )
       meterProvider = MeterProvider(resource=resource, metric_readers=[reader])
       metrics.set_meter_provider(meterProvider)
       TaskMetrics.meter = metrics.get_meter("pulpcore.task")

  #abstractmethod
  def store_metric(self,task):
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

  def store_metric(self,task):
    time_spent = (timezone.now() - task.pulp_created).total_seconds()
    self.wait_metric.add(
      time_spent,
      {"task.name": task.name,
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

  def store_metric(self, task):
    time_spent = (timezone.now() - task.started_at).total_seconds()
    self.running_metric.add(
      time_spent,
      {"task.name": task.name,
       "task.state": "running",
       "task.uuid": str(task.pulp_id),
       "task.worker": task.worker.name,
      }
    )

waiting_metric = WaitingMetric()
running_metric = RunningMetric()


# decorator to store the metric based on task method's name (dynamically retrieved)
# for now, this decorator will store the metric only after it changed its state
# for example, a tasking_waiting metric will be registered only after a waiting
# task gets into a running/failed/canceled state.
def store_metric(func):
  def wrapper(task):
    # [TODO] load telemetry bool from settings.py
    # and if it is not enabled, the decorator should just return func(task)
    # if telemetry:
    #   metric_method = getattr(sys.modules[__name__], task.state+"_metric")
    #   metric_method.store_metric(task)
    metric_method = getattr(sys.modules[__name__], task.state+"_metric")
    metric_method.store_metric(task)
    func(task)
  return wrapper