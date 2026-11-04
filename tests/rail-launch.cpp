// SPDX-License-Identifier: MIT
// Compile against the patched SDL source and FreeRDP development headers.
#include "sdl_rail_launch.hpp"
#include <sys/wait.h>
#include <cassert>
#include <iostream>
#include <filesystem>
static int calls=0;
static UINT execute(RailClientContext*,const RAIL_EXEC_ORDER* order)
{
 assert(std::string(order->RemoteApplicationProgram)=="C:\\Program Files\\Example\\app.exe");
 assert(std::string(order->RemoteApplicationArguments)=="\"C:\\space, comma\\café.txt\"");
 assert(std::string(order->RemoteApplicationWorkingDir)=="C:\\Program Files\\Example");
 ++calls;
 return CHANNEL_RC_OK;
}
int main()
{
 char dir[]="/tmp/wintide-rail-test-XXXXXX";
 assert(mkdtemp(dir)); setenv("XDG_RUNTIME_DIR",dir,1); setenv("WINTIDE_SESSION_REUSE","1",1);
 auto* settings=freerdp_settings_new(0); assert(settings);
 freerdp_settings_set_bool(settings,FreeRDP_RemoteApplicationMode,TRUE);
 freerdp_settings_set_string(settings,FreeRDP_ServerHostname,"test.invalid");
 freerdp_settings_set_string(settings,FreeRDP_Username,"fixture");
 freerdp_settings_set_string(settings,FreeRDP_RemoteApplicationProgram,"C:\\Program Files\\Example\\app.exe");
 freerdp_settings_set_string(settings,FreeRDP_RemoteApplicationCmdLine,"\"C:\\space, comma\\café.txt\"");
 freerdp_settings_set_string(settings,FreeRDP_RemoteApplicationWorkingDir,"C:\\Program Files\\Example");
 {
 SdlRailLaunch owner; assert(owner.prepare(settings)==0);
 RailClientContext rail{};rail.ClientExecute=execute;
 std::array<pid_t,3> children{};
 for(auto& child:children) {
  child=fork();assert(child>=0);
  if(child==0){SdlRailLaunch requester;_exit(requester.prepare(settings)==1 ? 0:1);}
 }
 for(int i=0;i<100 && calls<3;i++){owner.pollLaunch(&rail);usleep(10000);}
 assert(calls==3);
 for(auto child:children){int status=0;assert(waitpid(child,&status,0)==child);assert(WIFEXITED(status)&&WEXITSTATUS(status)==0);}
 // A different Windows identity gets a distinct connection.
 freerdp_settings_set_string(settings,FreeRDP_Username,"another-fixture");
 { SdlRailLaunch other; assert(other.prepare(settings)==0); }
 freerdp_settings_set_string(settings,FreeRDP_Username,"fixture");
 }
 // A released owner can be replaced despite a remaining lock file.
 { SdlRailLaunch replacement; assert(replacement.prepare(settings)==0); }
 // An insecure runtime directory must fail closed.
 chmod(dir,0777);{SdlRailLaunch unsafe;assert(unsafe.prepare(settings)==-1);}chmod(dir,0700);
 freerdp_settings_free(settings);
 // Cleanup only our generated fixtures.
 for(const auto& entry:std::filesystem::directory_iterator(dir))std::filesystem::remove(entry.path());
 rmdir(dir);
 std::cout << "PASS: concurrent handoff, exact arguments, identity isolation, owner cleanup, unsafe-directory refusal\n";
}
