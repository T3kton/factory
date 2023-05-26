from factory.plugins.builtin.ssh import ssh_exec

# plugin exports

SCRIPT_NAME = 'builtin'

SCRIPT_FUNCTIONS = {
                      'ssh_exec': ssh_exec,
                    }

SCRIPT_VALUES = {
                 }
