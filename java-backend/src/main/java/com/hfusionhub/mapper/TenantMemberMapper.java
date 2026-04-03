package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.TenantMember;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface TenantMemberMapper extends BaseMapper<TenantMember> {

    TenantMember selectByTenantAndUser(@Param("tenantId") Long tenantId,
                                       @Param("userId") Long userId);

    List<TenantMember> selectByTenantId(@Param("tenantId") Long tenantId);

    List<TenantMember> selectByUserId(@Param("userId") Long userId);
}
