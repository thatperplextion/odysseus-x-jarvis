"""
Test OS Operations for Jarvis OS
Comprehensive testing of filesystem and command execution capabilities
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from JARVIS.os_integration import OSOperations


async def test_os_operations():
    """Test all OS operations"""
    print("\n" + "="*60)
    print("TESTING OS OPERATIONS")
    print("="*60)
    
    # Initialize OS Operations
    print("\n1. Initializing OS Operations...")
    os_ops = OSOperations()
    os_ops.add_allowed_path(str(Path.home()), read_only=False)
    print("   [PASS] OS Operations initialized")
    
    # Test file operations
    print("\n2. Testing file operations...")
    
    # Create a test file
    test_file = Path.home() / "test_jarvis_os.txt"
    test_content = "Hello from Jarvis OS! This is a test file."
    
    print("   a. Writing file...")
    write_result = os_ops.write_file(str(test_file), test_content)
    if write_result.success:
        print(f"   [PASS] File written: {write_result.data['path']}")
    else:
        print(f"   [FAIL] Write failed: {write_result.error}")
        return False
    
    # Read the file
    print("   b. Reading file...")
    read_result = os_ops.read_file(str(test_file))
    if read_result.success:
        print(f"   [PASS] File read: {read_result.data['size']} bytes")
        print(f"   Content: {read_result.data['content']}")
    else:
        print(f"   [FAIL] Read failed: {read_result.error}")
        return False
    
    # Get file info
    print("   c. Getting file info...")
    info_result = os_ops.get_file_info(str(test_file))
    if info_result.success:
        print(f"   [PASS] File info: {info_result.data['name']} ({info_result.data['size']} bytes)")
    else:
        print(f"   [FAIL] File info failed: {info_result.error}")
        return False
    
    # Test directory operations
    print("\n3. Testing directory operations...")
    
    # Create a test directory
    test_dir = Path.home() / "test_jarvis_os_dir"
    print("   a. Creating directory...")
    dir_result = os_ops.create_directory(str(test_dir))
    if dir_result.success:
        print(f"   [PASS] Directory created: {dir_result.data['path']}")
    else:
        print(f"   [FAIL] Directory creation failed: {dir_result.error}")
        return False
    
    # List directory
    print("   b. Listing directory...")
    list_result = os_ops.list_directory(str(Path.home()))
    if list_result.success:
        print(f"   [PASS] Directory listed: {list_result.data['count']} items")
    else:
        print(f"   [FAIL] Directory listing failed: {list_result.error}")
        return False
    
    # Search files
    print("   c. Searching files...")
    search_result = os_ops.search_files(str(Path.home()), "*.txt", recursive=False)
    if search_result.success:
        print(f"   [PASS] Files found: {search_result.data['count']}")
    else:
        print(f"   [FAIL] File search failed: {search_result.error}")
        return False
    
    # Test command execution
    print("\n4. Testing command execution...")
    
    # Safe command
    print("   a. Executing safe command...")
    cmd_result = os_ops.execute_command("echo 'Hello from Jarvis OS!'")
    if cmd_result.success:
        print(f"   [PASS] Command executed")
        print(f"   Output: {cmd_result.data['stdout'].strip()}")
    else:
        print(f"   [FAIL] Command execution failed: {cmd_result.error}")
        return False
    
    # Test dangerous command blocking
    print("   b. Testing dangerous command blocking...")
    dangerous_result = os_ops.execute_command("rm -rf /")
    if not dangerous_result.success:
        print(f"   [PASS] Dangerous command blocked: {dangerous_result.error}")
    else:
        print(f"   [FAIL] Dangerous command was not blocked!")
        return False
    
    # Test operation history
    print("\n5. Testing operation history...")
    history = os_ops.get_operation_history(limit=10)
    print(f"   [PASS] Operation history: {len(history)} operations")
    
    # Cleanup
    print("\n6. Cleaning up...")
    if test_file.exists():
        test_file.unlink()
        print("   [PASS] Test file deleted")
    if test_dir.exists():
        test_dir.rmdir()
        print("   [PASS] Test directory deleted")
    
    print("\n" + "="*60)
    print("ALL OS OPERATIONS TESTS PASSED")
    print("="*60)
    return True


async def main():
    """Main test function"""
    try:
        success = await test_os_operations()
        if success:
            print("\n✅ OS Operations are fully functional!")
            sys.exit(0)
        else:
            print("\n❌ Some OS Operations tests failed")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
