from django.db import models
from django.core.exceptions import ValidationError

from cinp.orm_django import DjangoCInP as CInP

from factory.fields import name_regex
from factory.script import parser


cinp = CInP( 'Plans', '0.1' )


class PlanException( ValueError ):
  def __init__( self, code, message ):
    super().__init__( message )
    self.message = message
    self.code = code

  @property
  def response_data( self ):
    return { 'exception': 'PlanException', 'error': self.code, 'message': self.message }

  def __str__( self ):
    return 'PlanException ({0}): {1}'.format( self.code, self.message )


@cinp.model()
class Drawing( models.Model ):
  name = models.CharField( max_length=200, primary_key=True )
  description = models.CharField( max_length=250 )
  part_query = models.CharField( max_length=500, blank=True )
  script = models.TextField()
  updated = models.DateTimeField( editable=False, auto_now=True )
  created = models.DateTimeField( editable=False, auto_now_add=True )

  @cinp.check_auth()
  @staticmethod
  def checkAuth( user, verb, id_list, action=None ):
    return cinp.basic_auth_check( user, verb, action, Drawing )

  def clean( self, *args, **kwargs ):
    super().clean( *args, **kwargs )
    errors = {}

    if self.name and not name_regex.match( self.name ):
      errors[ 'name' ] = 'Invalid'

    results = parser.lint( self.script )
    if results is not None:
      errors[ 'script' ] = 'invalid'

    if errors:
      raise ValidationError( errors )

  class Meta:
    pass
    # default_permissions = ( 'add', 'change', 'delete', 'view' )

  def __str__( self ):
    return 'Drawing "{0}"({1})'.format( self.description, self.name )
