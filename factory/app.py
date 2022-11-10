import os
from django.conf import settings

from cinp.server_werkzeug import WerkzeugServer, NoCINP

from factory import plugins
from factory.Auth.models import getUser

# get plugins
plugin_list = []
plugin_dir = os.path.dirname( plugins.__file__ )
for item in os.scandir( plugin_dir ):
  if not item.is_dir() or not os.path.exists( os.path.join( plugin_dir, item.name, 'models.py' ) ):
    continue
  plugin_list.append( 'factory.plugins.{0}'.format( item.name ) )


def get_app( debug ):
  extras = {}
  if settings.UI_HOSTNAME is not None:
    extras[ 'cors_allow_origin' ] = settings.UI_HOSTNAME

  app = WerkzeugServer( root_path='/api/v1/', root_version='1.0', debug=debug, get_user=getUser, auth_header_list=[ 'AUTH-TOKEN', 'AUTH-ID' ], auth_cookie_list=[ 'SESSION' ], debug_dump_location=settings.DEBUG_DUMP_LOCATION, **extras )

  app.registerNamespace( '/', 'factory.Auth' )
  app.registerNamespace( '/', 'factory.Plan' )
  app.registerNamespace( '/', 'factory.WorkOrder' )
  app.registerNamespace( '/', 'factory.Assembler' )

  for plugin in plugin_list:
    try:
      app.registerNamespace( '/', plugin )
    except NoCINP:
      pass

  app.validate()

  return app
