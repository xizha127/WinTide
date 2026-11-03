#include "vmaware.hpp"
#include <iostream>
int main() {
#define CHECK(f) try { std::cout << #f << "=" << VM::check(VM::f) << std::endl; } catch (...) { std::cout << #f << "=ERROR" << std::endl; }
CHECK(HYPERVISOR_BIT)
CHECK(HYPERVISOR_STR)
CHECK(CPUID_SIGNATURE)
CHECK(SMBIOS_VM_BIT)
CHECK(MAC)
return 0;
}
