from cinp.orm_django import DjangoCInP as CInP

from factory.WorkOrder.lib import processJobs, jobResults, jobError

cinp = CInP( 'Assembler', '0.1' )


# these are only for subcontractor to talk to, thus some of the job_id short cuts
@cinp.staticModel()  # TODO: move to  Foreman?
class Assembler():
  def __init__( self ):
    super().__init__()

  @cinp.action( return_type={ 'type': 'Map', 'is_array': True }, paramater_type_list=[  { 'type': 'String', 'is_array': True }, 'Integer' ] )
  @staticmethod
  def getJobs( module_list, max_jobs=10 ):
    result = processJobs( module_list, max_jobs )
    return result

  @cinp.action( return_type='String', paramater_type_list=[ 'Integer', 'String', 'Map' ] )
  @staticmethod
  def jobResults( job_id, cookie, data ):
    return jobResults( job_id, cookie, data )

  @cinp.action( paramater_type_list=[ 'Integer', 'String', 'String' ] )
  @staticmethod
  def jobError( job_id, cookie, msg ):
    jobError( job_id, cookie, msg )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, verb, id_list, action=None ):
    if verb == 'DESCRIBE':
      return True

    return verb == 'CALL' and user.username == 'assembler'
