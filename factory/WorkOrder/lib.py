import pickle
import copy

from pymongo import MongoClient
from django.utils import timezone
from django.conf import settings

from factory.script.parser import Parser
from factory.script.runner import Runner, Pause, ExecutionError, UnrecoverableError, ParamaterError, NotDefinedError, ScriptError


from factory.WorkOrder.models import WorkOrder, Job, WorkOrderException

MAX_PART_LIST_SIZE = 100

_mongo_db = None


def _connect():
  global _mongo_db
  if _mongo_db is not None:
    return _mongo_db

  _mongo_db = MongoClient( settings.MONGO_HOST ).contractor.structure
  return _mongo_db


def get_part_list( query, max_results ):
  if not query:
    return []

  db = _connect()
  part_list = list( db.find( filter=query, limit=max_results ) )
  return part_list


class WorkOrderPlugin( object ):
  SCRIPT_NAME = 'workorder'

  def __init__( self, workorder ):
    super().__init__()
    if isinstance( workorder, int ):
      self.workorder_pk = workorder
      self.workorder = WorkOrder.objects.get( pk=self.workorder_pk )

    else:
      self.workorder = workorder
      self.workorder_pk = self.workorder.pk

  def getValues( self ):
    result = {}
    result[ 'options' ] = self.workorder.options

    return result

  def getFunctions( self ):
    result = {}

    return result

  def __reduce__( self ):
    return ( self.__class__, ( self.workorder_pk, ) )


class PartPlugin( object ):
  SCRIPT_NAME = 'part'

  def __init__( self, part, values ):
    super().__init__()
    self.part = part
    self.values = copy.deepcopy( values.copy() )

  def getValues( self ):
    result = {}
    result[ 'part' ] = self.part
    result[ 'values' ] = self.values

    return result

  def getFunctions( self ):
    result = {}

    return result

  def __reduce__( self ):
    return ( self.__class__, ( self.part, self.values ) )


def _createJob( workorder, part, value_map ):
  parser = Parser()
  runner = Runner( parser.parse( workorder.script ) )

  # for module in RUNNER_MODULE_LIST:
  #   runner.registerModule( module )

  # for module in ( 'factory.WorkOrder.runner_plugins', ):
  #   runner.registerModule( module )

  runner.registerObject( PartPlugin( part ) )
  runner.registerObject( WorkOrderPlugin( workorder ) )

  job = Job( workorder=workorder, part=part[ '_id' ], values=value_map )
  job.state = 'new'
  job.script_runner = pickle.dumps( runner )
  job.full_clean()
  job.save()


def processJobs( module_list, max_jobs=10 ):
  if max_jobs > 100:
    max_jobs = 100

  # start waiting jobs
  for job in Job.objects.select_for_update().filter( state='waiting' ):
    job.state = 'queued'
    job.started_at = timezone.now()
    job.full_clean()
    job.save()

    # JobLog.started( job )

  # clean up completed jobs
  for job in Job.objects.select_for_update().filter( state='done' ):
    job.finished_at = timezone.now()
    job.full_clean()
    job.save()

    # JobLog.finished( job )

  # iterate over the curent jobs
  results = []
  for job in Job.objects.select_for_update().filter( state='queued' ).order_by( 'updated' ):
    runner = pickle.loads( job.script_runner )

    if runner.aborted:
      job.state = 'aborted'
      job.full_clean()
      job.save()
      continue

    if runner.done:
      job.state = 'done'
      job.full_clean()
      job.save()
      continue

    try:
      msg = runner.run()
      if msg != 'Not Complete':  # TODO: this is ugly!! need a better way for the runner to say nothing, and/or the Interrupt to not have a user message, the job might post a message and the `is complete` system will stomp on  it
        job.message = msg

    except Pause as e:
      job.state = 'paused'
      job.message = str( e )[ 0:1024 ]

    except ExecutionError as e:
      job.state = 'error'
      job.message = str( e )[ 0:1024 ]

    except ( UnrecoverableError, ParamaterError, NotDefinedError, ScriptError ) as e:
      job.state = 'aborted'
      job.message = str( e )[ 0:1024 ]

    except Exception as e:
      job.state = 'aborted'
      job.message = 'Unknown Runtime Exception ({0}): "{1}"'.format( type( e ).__name__, str( e ) )[ 0:1024 ]

    if job.state == 'queued':
      task = runner.toAssembler( module_list )
      if task is not None:
        task.update( { 'job_id': job.pk } )
        results.append( task )

    job.status = runner.status
    job.script_runner = pickle.dumps( runner )
    job.full_clean()
    job.save()

    if len( results ) >= max_jobs:
      break

  return results


# TODO: we will need some kind of job record locking, so only one thing can happen at a time, ie: rolling back when things are still comming in,
#   trying to handler.run() when fromAssembler is happening, pretty much, anything the runner is unpickled, nothing else should  happen to
#   the job till it is pickled and saved
def jobResults( job_id, cookie, data ):
  try:
    job = Job.objects.select_for_update().get( pk=job_id )
  except Job.DoesNotExist:
    raise WorkOrderException( 'JOB_NOT_FOUND', 'Error saving job results: "Job Not Found"' )

  # TODO: check the curent job state to make sure we don't undo something with the job.status = runner.status
  runner = pickle.loads( job.script_runner )
  ( result, message ) = runner.fromAssembler( cookie, data )
  if result != 'Accepted':  # it wasn't valid/taken, no point in saving anything
    raise WorkOrderException( 'INVALID_RESULT', 'Error saving job results: "{0}"'.format( result ) )

  job.status = runner.status
  if message is None:
    job.message = ''
  else:
    job.message = message
  job.script_runner = pickle.dumps( runner )
  job.full_clean()
  job.save()

  return result


def jobError( job_id, cookie, msg ):
  try:
    job = Job.objects.select_for_update().get( pk=job_id )
  except Job.DoesNotExist:
    raise WorkOrderException( 'JOB_NOT_FOUND', 'Error setting job to error: "Job Not Found"' )

  job = job.realJob
  runner = pickle.loads( job.script_runner )
  if cookie != runner.assembler_cookie:  # we do our own out of bad cookie check b/c this type of error dosen't need to be propagated to the script runner
    raise WorkOrderException( 'BAD_COOKIE', 'Error setting job to error: "Bad Cookie"' )

  job.message = msg[ 0:1024 ]
  job.state = 'error'
  job.full_clean
  job.save()
