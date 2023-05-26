from factory.script.runner import ExternalFunction


class ssh_exec( ExternalFunction ):
  def __init__( self, *args, **kwargs ):
    super().__init__( *args, **kwargs )
    self.host = None
    self.rc = None

  @property
  def done( self ):
    return self.rc is not None

  @property
  def message( self ):
    if self.rc is not None:
      return 'Execution Returned "{0}"'.format( self.rc )
    else:
      return 'Waiting for Execution Results'

  @property
  def value( self ):
    return True

  def setup( self, parms ):
    pass

  def toSubcontractor( self ):
    return ( 'ssh_exec', { 'host': self.host } )

  def fromSubcontractor( self, data ):
    self.rc = data[ 'rc' ]

  def __getstate__( self ):
    return ( self.host, self.rc )

  def __setstate__( self, state ):
    self.host = state[0]
    self.rc = state[1]
