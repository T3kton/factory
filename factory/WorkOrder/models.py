import pickle
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from factory.fields import MapField, JSONField
from factory.Plan.models import Drawing

PICKLE_PROTOCOL = 4
MAX_TARGET_PARTS = 100
WORKORDER_EXECUTION_STYLE_CHOICES = ( 'parallel', 'serial' )
JOB_STATE_CHOICES = ( 'new', 'queued', 'waiting', 'done', 'paused', 'error', 'aborted' )

cinp = CInP( 'WorkOrder', '0.1' )


class WorkOrderException( ValueError ):
  def __init__( self, code, message ):
    super().__init__( message )
    self.message = message
    self.code = code

  @property
  def response_data( self ):
    return { 'exception': 'WorkOrderException', 'error': self.code, 'message': self.message }

  def __str__( self ):
    return 'WorkOrderException ({0}): {1}'.format( self.code, self.message )


@cinp.model( not_allowed_verb_list=( 'CREATE', 'DELETE', 'UPDATE' ), constant_set_map={ 'execution_style': WORKORDER_EXECUTION_STYLE_CHOICES }, read_only_list=( 'results', ) )
class WorkOrder( models.Model ):
  name = models.CharField( max_length=200 )
  script = models.TextField()
  part_query = models.CharField( max_length=500 )
  execution_style = models.CharField( max_length=10, choices=[ ( i, i ) for i in WORKORDER_EXECUTION_STYLE_CHOICES ])
  options = MapField( blank=True, null=True )
  user = models.CharField( max_length=150 )  # max length from the django.contrib.auth User.username, or should this be a protected foreign key
  started_at = models.DateTimeField( blank=True, null=True )
  finished_at = models.DateTimeField( blank=True, null=True )
  updated = models.DateTimeField( editable=False, auto_now=True )
  created = models.DateTimeField( editable=False, auto_now_add=True )

  @cinp.action( return_type={ 'type': 'Model', 'model': 'factory.WorkOrder.models.WorkOrder' }, paramater_type_list=[ '_USER_', { 'type': 'Model', 'model': Drawing }, { 'type': 'String', 'choices': WORKORDER_EXECUTION_STYLE_CHOICES }, 'String', 'Map' ] )
  @staticmethod
  def new( user, drawing, execution_style, part_query=None, options=None ):
    options = options or {}

    if drawing.part_query:
      if part_query:
        raise WorkOrderException( 'QUERY_NOT_ALLOWED', 'Drawing does not allow part queries' )

      part_query = drawing.part_query

    if not part_query:
        raise WorkOrderException( 'QUERY_REQUIRED', 'part_query required' )

    workorder = WorkOrder( user=user.username, name=drawing.name, script=drawing.script, part_query=part_query, execution_style=execution_style, options=options )
    workorder.full_clean()
    workorder.save()

    if part_query:
      from factory.WorkOrder.lib import get_part_list, _createJob

      part_list = get_part_list( part_query, MAX_TARGET_PARTS + 1 )
      if len( part_list ) > MAX_TARGET_PARTS:
        raise WorkOrderException( 'TO_MANY_PARTS', 'The party query returned to many parts, max: {0}'.format( MAX_TARGET_PARTS ) )

      for part in part_list:
        _createJob( workorder, part )

    return workorder

  # not called via API
  def checkFinished( self ):
    if self.started_at is None or self.finished_at is not None:
      return

    finished = True
    for job in self.job_set.all():
      finished &= job.finished_at is not None

    if finished:
      self.finished_at = timezone.now()
      self.full_clean()
      self.save()

  @cinp.action()
  def start( self ):
    if self.started_at is not None or self.finished_at is not None:
      return

    for job in self.job_set.select_for_update().all():
      job.state = 'waiting'
      job.full_clean()
      job.save()

    self.started_at = timezone.now()
    self.full_clean()
    self.save()

  @cinp.action()
  def pause( self ):
    if self.started_at is None or self.finished_at is not None:
      return

    for job in self.job_set.select_for_update().all():
      job.state = 'pause'
      job.full_clean()
      job.save()

  @cinp.action()
  def resume( self ):
    if self.started_at is None or self.finished_at is not None:
      return

    for job in self.job_set.select_for_update().all():
      if job.state == 'paused':
        job.state = 'queued'
        job.full_clean()
        job.save()

  @cinp.action()
  def abort( self ):
    if self.finished_at is not None:  # can abort before it starts
      return

    for job in self.job_set.select_for_update().all():
      job.state = 'aborted'
      job.full_clean()
      job.save()

    self.finished_at = timezone.now()
    self.full_clean()
    self.save()

  @cinp.action( 'Map' )
  def getResults( self ):
    results = {}
    for job in self.job_set.all():
      results[ job.part ] = '({0}{1})'.format( job.state, job.message )

    return results

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, verb, id_list, action=None ):
    return cinp.basic_auth_check( user, verb, action, WorkOrder )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.execution_style not in WORKORDER_EXECUTION_STYLE_CHOICES:
      errors[ 'type' ] = 'Invalid'

    if errors:
      raise ValidationError( errors )

  class Meta:
    pass
    # default_permissions = ( 'add', 'change', 'delete', 'view' )

  def __str__( self ):
    return 'WorkOrder for "{0}" on "{1}"'.format( self.name, self.part_query )


@cinp.model( not_allowed_verb_list=( 'CREATE', 'DELETE', 'UPDATE' ), hide_field_list=( 'script_runner', ) )
class Job( models.Model ):
  workorder = models.ForeignKey( WorkOrder, on_delete=models.PROTECT )
  part = models.CharField( max_length=200, blank=True, null=True )
  state = models.CharField( max_length=10, choices=[ ( i, i ) for i in JOB_STATE_CHOICES ] )
  values = MapField()
  status = JSONField( default=[], blank=True )
  message = models.CharField( max_length=1024, default='', blank=True )
  script_runner = models.BinaryField( editable=False )
  started_at = models.DateTimeField( blank=True, null=True )
  finished_at = models.DateTimeField( blank=True, null=True )
  updated = models.DateTimeField( editable=False, auto_now=True )
  created = models.DateTimeField( editable=False, auto_now_add=True )

  @cinp.action()
  def pause( self ):
    """
    Pause a job that is in 'queued' state state.

    Errors:
      NOT_PAUSEABLE - Job is not in state 'queued'.
    """
    if self.state != 'queued':
      raise WorkOrderException( 'NOT_PAUSEABLE', 'Can only pause a job if it is queued' )

    self.state = 'paused'
    self.full_clean()
    self.save()

  @cinp.action()
  def resume( self ):
    """
    Resume a job that is in 'paused' state state.

    Errors:
      NOT_PAUSED - Job is not in state 'paused'.
    """
    if self.state != 'paused':
      raise WorkOrderException( 'NOT_PAUSED', 'Can only resume a job if it is paused' )

    self.state = 'queued'
    self.full_clean()
    self.save()

  @cinp.action()
  def reset( self ):
    """
    Resets a job that is in 'error' state, this allows the job to try the failed step again.

    Errors:
      NOT_ERRORED - Job is not in state 'error'.
    """
    if self.state != 'error':
      raise WorkOrderException( 'NOT_ERRORED', 'Can only reset a job if it is in error' )

    runner = pickle.loads( self.script_runner )
    runner.clearDispatched()
    self.status = runner.status
    self.script_runner = pickle.dumps( runner, protocol=PICKLE_PROTOCOL )

    self.state = 'queued'
    self.full_clean()
    self.save()

  @cinp.action()
  def rollback( self ):
    """
    Starts the rollback for jobs that are in state 'error'.

    Errors:
      NOT_ERRORED - Job is not in state 'error'.
    """
    if self.state != 'error':
      raise WorkOrderException( 'NOT_ERRORED', 'Can only rollback a job if it is in error' )

    runner = pickle.loads( self.script_runner )
    msg = runner.rollback()
    if msg != 'Done':
      raise ValueError( 'Unable to rollback "{0}"'.format( msg ) )

    self.status = runner.status
    self.script_runner = pickle.dumps( runner, protocol=PICKLE_PROTOCOL )
    self.state = 'queued'
    self.full_clean()
    self.save()

  @cinp.action()
  def clearDispatched( self ):
    """
    Resets a job that is in 'queued' state, and assembler lost the job.  Make
    sure to verify that assembler has lost the job results before calling this.

    Errors:
      NOT_ERRORED - Job is not in state 'queued'.
    """
    if self.state != 'queued':
      raise WorkOrderException( 'NOT_ERRORED', 'Can only clear the dispatched flag a job if it is in queued state' )

    runner = pickle.loads( self.script_runner )
    runner.clearDispatched()
    self.status = runner.status
    self.script_runner = pickle.dumps( runner, protocol=PICKLE_PROTOCOL )

    self.full_clean()
    self.save()

  @cinp.action( return_type={ 'type': 'Map' } )
  @staticmethod
  def jobStats():
    """
    Returns the job status
    """
    return { 'running': Job.objects.count(), 'error': Job.objects.filter( state__in=( 'error', 'aborted', 'paused' ) ).count() }

  @cinp.action( return_type={ 'type': 'Map' } )
  def jobRunnerVariables( self ):
    """
    Returns variables internal to the job script
    """
    result = {}
    runner = pickle.loads( self.script_runner )

    for module in runner.value_map:
      for name in runner.value_map[ module ]:
        result[ '{0}.{1}'.format( module, name ) ] = str( runner.value_map[ module ][ name ][0]() )

    result.update( runner.variable_map )

    return result

  @cinp.action( return_type={ 'type': 'Map' } )
  def jobRunnerState( self ):
    """
    Returns the state of the job script
    """
    result = {}
    runner = pickle.loads( self.script_runner )
    result[ 'script' ] = self.workorder.script
    result[ 'cur_line' ] = runner.cur_line
    result[ 'state' ] = runner.state

    return result

  @cinp.action( return_type='String', paramater_type_list=[ 'String' ] )
  def signalComplete( self, cookie ):
    runner = pickle.loads( self.script_runner )

    for entry in runner.object_list:
      if entry.__class__.__name__ == 'SignalingPlugin':
        result = entry.signal( cookie )
        self.script_runner = pickle.dumps( runner, protocol=PICKLE_PROTOCOL )
        self.full_clean()
        self.save()
        return result

    return 'No Reciever'

  @cinp.action( return_type='String', paramater_type_list=[ 'String' ] )
  def signalAlert( self, msg ):
    self.message = msg[ 0:1024 ]
    if self.status in ( 'queued', 'paused' ):
      self.status = 'error'

    self.full_clean()
    self.save()

    return 'Alerted'

  @cinp.action( return_type='String', paramater_type_list=[ 'String' ] )
  def postMessage( self, msg ):
    self.message = msg[ 0:1024 ]
    self.full_clean()
    self.save()

    return 'Posted'

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, verb, id_list, action=None ):
    return cinp.basic_auth_check( user, verb, action, Job )

  def clean( self, *args, **kwargs ):  # TODO: also need to make sure a Structure is in only one complex
    super().clean( *args, **kwargs )
    errors = {}

    if self.state not in JOB_STATE_CHOICES:
      errors[ 'state' ] = 'Invalid state "{0}"'.format( self.state )

    if errors:
      raise ValidationError( errors )

  class Meta:
    default_permissions = ()  # only CALL
    permissions = (
                    ( 'can_base_job', 'Can Work With Base Jobs' ),
                    ( 'can_job_signal', 'Can call the Job Signalling Actions' )
                  )

  def __str__( self ):
    return 'Job #{0} for "{1}"'.format( self.pk, self.workorder.pk )
