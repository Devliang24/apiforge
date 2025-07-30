"""Real OpenAPI Processing and Task Generation"""

import asyncio
import json
import uuid
import httpx
import yaml
from datetime import datetime
from typing import Dict, List, Any, Optional
import aiosqlite
from urllib.parse import urljoin, urlparse

from apiforge.logger import get_logger
from apiforge.web.worker_manager import worker_manager, WorkerType

logger = get_logger(__name__)


class OpenAPIProcessor:
    """Real OpenAPI specification processor"""
    
    def __init__(self, db_path: str = ".apiforge/queue.db"):
        self.db_path = db_path
        
    async def fetch_openapi_spec(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse OpenAPI specification from URL"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching OpenAPI spec from: {url}")
                response = await client.get(url)
                response.raise_for_status()
                
                content_type = response.headers.get('content-type', '').lower()
                
                if 'application/json' in content_type:
                    spec = response.json()
                elif 'yaml' in content_type or 'yml' in content_type:
                    spec = yaml.safe_load(response.text)
                else:
                    # Try to guess format
                    try:
                        spec = response.json()
                    except:
                        spec = yaml.safe_load(response.text)
                
                logger.info(f"Successfully parsed OpenAPI spec with {len(spec.get('paths', {}))} paths")
                return spec
                
        except Exception as e:
            logger.error(f"Failed to fetch OpenAPI spec from {url}: {e}")
            return None
    
    def extract_endpoints(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract endpoint information from OpenAPI spec"""
        endpoints = []
        base_path = spec.get('basePath', '')
        servers = spec.get('servers', [])
        
        # Determine base URL
        base_url = ""
        if servers:
            base_url = servers[0].get('url', '')
        
        paths = spec.get('paths', {})
        
        for path, path_obj in paths.items():
            if isinstance(path_obj, dict):
                for method, operation in path_obj.items():
                    if method.upper() in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']:
                        endpoint_info = {
                            'path': path,
                            'method': method.upper(),
                            'operation_id': operation.get('operationId', f"{method}_{path.replace('/', '_')}"),
                            'summary': operation.get('summary', ''),
                            'description': operation.get('description', ''),
                            'parameters': operation.get('parameters', []),
                            'request_body': operation.get('requestBody', {}),
                            'responses': operation.get('responses', {}),
                            'tags': operation.get('tags', []),
                            'security': operation.get('security', []),
                            'base_url': base_url,
                            'full_path': urljoin(base_url, base_path + path)
                        }
                        endpoints.append(endpoint_info)
        
        logger.info(f"Extracted {len(endpoints)} endpoints from OpenAPI spec")
        return endpoints
    
    async def create_tasks_from_endpoints(self, project_id: str, endpoints: List[Dict[str, Any]]) -> int:
        """Create database tasks from extracted endpoints"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                created_count = 0
                
                for endpoint in endpoints:
                    task_id = str(uuid.uuid4())
                    now = datetime.now().isoformat()
                    
                    # Determine task priority based on method
                    priority_map = {
                        'GET': 3,    # Medium
                        'POST': 2,   # High  
                        'PUT': 2,    # High
                        'DELETE': 2, # High
                        'PATCH': 3,  # Medium
                        'HEAD': 4,   # Low
                        'OPTIONS': 5 # Very Low
                    }
                    priority = priority_map.get(endpoint['method'], 3)
                    
                    # Store complete endpoint data
                    endpoint_data = json.dumps(endpoint)
                    
                    await db.execute("""
                        INSERT INTO tasks (
                            task_id, session_id, priority, status,
                            endpoint_path, endpoint_method, endpoint_data,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        task_id, project_id, priority, 'pending',
                        endpoint['path'], endpoint['method'], endpoint_data,
                        now, now
                    ))
                    
                    created_count += 1
                
                await db.commit()
                logger.info(f"Created {created_count} tasks for project {project_id}")
                return created_count
                
        except Exception as e:
            logger.error(f"Failed to create tasks from endpoints: {e}")
            return 0


class RealTaskProcessor:
    """Real task processing with worker assignment"""
    
    def __init__(self, db_path: str = ".apiforge/queue.db"):
        self.db_path = db_path
        self.openapi_processor = OpenAPIProcessor(db_path)
        
    async def start_real_generation(self, project_id: str, url: str, output_file: str) -> bool:
        """Start real test generation process"""
        try:
            logger.info(f"Starting real generation for project {project_id} from {url}")
            
            # Update project status
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE sessions 
                    SET status = 'active', updated_at = ?
                    WHERE session_id = ?
                """, (datetime.now().isoformat(), project_id))
                await db.commit()
            
            # Step 1: Fetch and parse OpenAPI spec
            spec = await self.openapi_processor.fetch_openapi_spec(url)
            if not spec:
                await self._mark_project_failed(project_id, "Failed to fetch OpenAPI specification")
                return False
            
            # Step 2: Extract endpoints
            endpoints = self.openapi_processor.extract_endpoints(spec)
            if not endpoints:
                await self._mark_project_failed(project_id, "No endpoints found in OpenAPI specification")
                return False
            
            # Step 3: Create tasks in database
            task_count = await self.openapi_processor.create_tasks_from_endpoints(project_id, endpoints)
            if task_count == 0:
                await self._mark_project_failed(project_id, "Failed to create tasks from endpoints")
                return False
            
            # Step 4: Start processing tasks with workers
            asyncio.create_task(self._process_project_tasks(project_id))
            
            logger.info(f"Real generation started successfully for project {project_id} with {task_count} tasks")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start real generation for project {project_id}: {e}")
            await self._mark_project_failed(project_id, str(e))
            return False
    
    async def _process_project_tasks(self, project_id: str):
        """Process all tasks for a project using worker assignment"""
        try:
            logger.info(f"Starting task processing for project {project_id}")
            
            while True:
                # Get pending tasks
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute("""
                        SELECT task_id, endpoint_method, endpoint_path, endpoint_data
                        FROM tasks 
                        WHERE session_id = ? AND status = 'pending'
                        ORDER BY priority ASC, created_at ASC
                        LIMIT 10
                    """, (project_id,))
                    
                    pending_tasks = await cursor.fetchall()
                
                if not pending_tasks:
                    # Check if all tasks are completed
                    async with aiosqlite.connect(self.db_path) as db:
                        cursor = await db.execute("""
                            SELECT 
                                COUNT(*) as total,
                                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
                            FROM tasks WHERE session_id = ?
                        """, (project_id,))
                        
                        stats = await cursor.fetchone()
                        total, completed, failed = stats
                        
                        if completed + failed == total:
                            # All tasks done
                            final_status = 'completed' if failed == 0 else 'partially_completed'
                            await self._mark_project_completed(project_id, final_status)
                            logger.info(f"Project {project_id} processing completed: {completed} succeeded, {failed} failed")
                            break
                        else:
                            # Wait for more tasks to become available or complete
                            await asyncio.sleep(2)
                            continue
                
                # Assign tasks to available workers
                for task_id, method, path, endpoint_data in pending_tasks:
                    # Determine preferred worker type based on operation
                    preferred_type = self._get_preferred_worker_type(method, endpoint_data)
                    
                    # Try to assign to worker
                    assigned_worker = await worker_manager.assign_task(task_id, preferred_type)
                    
                    if assigned_worker:
                        # Simulate task processing (in real implementation, this would be handled by the worker)
                        asyncio.create_task(self._simulate_task_processing(task_id, endpoint_data))
                    else:
                        logger.warning(f"No available workers for task {task_id}, will retry later")
                
                # Wait before checking for more tasks
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error processing tasks for project {project_id}: {e}")
            await self._mark_project_failed(project_id, f"Task processing error: {e}")
    
    def _get_preferred_worker_type(self, method: str, endpoint_data: str) -> WorkerType:
        """Determine preferred worker type based on endpoint characteristics"""
        try:
            data = json.loads(endpoint_data)
            
            # Complex endpoints with request bodies prefer LLM workers
            if data.get('request_body') or method in ['POST', 'PUT', 'PATCH']:
                return WorkerType.LLM_PROCESSOR
            
            # Simple GET endpoints can use general workers
            return WorkerType.GENERAL
            
        except:
            return WorkerType.GENERAL
    
    async def _simulate_task_processing(self, task_id: str, endpoint_data: str):
        """Simulate task processing (replace with real worker communication)"""
        try:
            # Parse endpoint data
            endpoint = json.loads(endpoint_data)
            
            # Simulate processing time based on complexity
            base_time = 2
            if endpoint.get('request_body'):
                base_time += 2
            if len(endpoint.get('parameters', [])) > 5:
                base_time += 1
            
            await asyncio.sleep(base_time)
            
            # Generate mock test cases
            test_cases = self._generate_mock_test_cases(endpoint)
            
            # Mark task as completed
            success = await worker_manager.complete_task(
                task_id, 
                success=True,
                result={
                    "test_cases": test_cases,
                    "endpoint": f"{endpoint['method']} {endpoint['path']}",
                    "generated_count": len(test_cases)
                }
            )
            
            if success:
                logger.debug(f"Task {task_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}")
            await worker_manager.complete_task(task_id, success=False, error=str(e))
    
    def _generate_mock_test_cases(self, endpoint: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate mock test cases based on endpoint info"""
        test_cases = []
        method = endpoint['method']
        path = endpoint['path']
        
        # Generate positive test case
        test_cases.append({
            "id": f"TC_{uuid.uuid4().hex[:8]}",
            "name": f"{method} {path} - Success Case",
            "description": f"Test successful {method} request to {path}",
            "category": "positive",
            "priority": "High",
            "request": {
                "method": method,
                "endpoint": path,
                "headers": {"Content-Type": "application/json"},
                "pathParams": {},
                "queryParams": {},
                "body": {} if method in ['POST', 'PUT', 'PATCH'] else None
            },
            "expectedResponse": {
                "statusCode": 200 if method != 'POST' else 201,
                "headers": {"Content-Type": "application/json"},
                "bodySchema": {}
            }
        })
        
        # Generate negative test case for methods with bodies
        if method in ['POST', 'PUT', 'PATCH']:
            test_cases.append({
                "id": f"TC_{uuid.uuid4().hex[:8]}",
                "name": f"{method} {path} - Invalid Data",
                "description": f"Test {method} request with invalid data",
                "category": "negative", 
                "priority": "Medium",
                "request": {
                    "method": method,
                    "endpoint": path,
                    "headers": {"Content-Type": "application/json"},
                    "body": {"invalid": "data"}
                },
                "expectedResponse": {
                    "statusCode": 400,
                    "bodySchema": {"type": "object", "properties": {"error": {"type": "string"}}}
                }
            })
        
        # Add boundary test for GET endpoints with parameters
        if method == 'GET' and endpoint.get('parameters'):
            test_cases.append({
                "id": f"TC_{uuid.uuid4().hex[:8]}",
                "name": f"{method} {path} - Boundary Values",
                "description": f"Test {method} request with boundary parameter values",
                "category": "boundary",
                "priority": "Medium",
                "request": {
                    "method": method,
                    "endpoint": path,
                    "queryParams": {"limit": 1000, "offset": 0}
                },
                "expectedResponse": {
                    "statusCode": 200,
                    "bodySchema": {"type": "array"}
                }
            })
        
        return test_cases
    
    async def _mark_project_failed(self, project_id: str, error: str):
        """Mark project as failed"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE sessions 
                    SET status = 'failed', updated_at = ?, metadata = json_set(COALESCE(metadata, '{}'), '$.error', ?)
                    WHERE session_id = ?
                """, (datetime.now().isoformat(), error, project_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to mark project {project_id} as failed: {e}")
    
    async def _mark_project_completed(self, project_id: str, status: str = 'completed'):
        """Mark project as completed"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE sessions 
                    SET status = ?, updated_at = ?
                    WHERE session_id = ?
                """, (status, datetime.now().isoformat(), project_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to mark project {project_id} as completed: {e}")


# Global processor instance
real_processor = RealTaskProcessor()